from flask import Flask, render_template, request, send_from_directory, jsonify, session, redirect, url_for
from flask_compress import Compress
import os
import base64
import hashlib
import hmac
import struct
import time
from database import DatabaseManager
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
from uuid import uuid4
from urllib.parse import quote

# Handle PIL/Pillow import compatibility
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    try:
        # Try importing from the Pillow package
        from PIL import Image
        PIL_AVAILABLE = True
    except ImportError:
        # If both fail, set a flag and continue without image processing
        PIL_AVAILABLE = False
        print("Warning: PIL/Pillow not available. Image processing disabled.")
    except Exception as e:
        PIL_AVAILABLE = False
        print(f"Error importing PIL: {e}")
        # Create a dummy Image class to prevent other errors
        class Image:
            def __init__(self, *args, **kwargs):
                pass
            @staticmethod
            def open(*args, **kwargs):
                raise NotImplementedError("Image processing not available")

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this for production!
Compress(app)
db = DatabaseManager()

# Optional noindex header (enabled only when BLOCK_INDEXING=true)
@app.after_request
def add_noindex_headers(response):
    if os.environ.get('BLOCK_INDEXING', '').lower() in ('1', 'true', 'yes'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, nosnippet, noarchive, notranslate, noimageindex'
    return response

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            return redirect(url_for('admin'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        # Backward compatibility for sessions created before role support.
        if 'user_role' not in session:
            session['user_role'] = 'admin'
        return f(*args, **kwargs)
    return decorated_function

def get_client_ip():
    """Get client IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def generate_totp_secret():
    """Create a base32 TOTP secret."""
    return base64.b32encode(os.urandom(20)).decode('utf-8').rstrip('=')

def _normalize_base32(secret):
    normalized = (secret or '').strip().replace(' ', '').upper()
    if not normalized:
        return ''
    padding = '=' * ((8 - (len(normalized) % 8)) % 8)
    return normalized + padding

def generate_totp_code(secret, for_time=None):
    key = base64.b32decode(_normalize_base32(secret), casefold=True)
    timestamp = int(for_time if for_time is not None else time.time())
    counter = timestamp // 30
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    ) % 1000000
    return f'{code_int:06d}'

def verify_totp_code(secret, code, window=1):
    if not secret:
        return False
    normalized_code = ''.join(ch for ch in (code or '') if ch.isdigit())
    if len(normalized_code) != 6:
        return False
    now = int(time.time())
    for offset in range(-window, window + 1):
        candidate = generate_totp_code(secret, now + (offset * 30))
        if hmac.compare_digest(candidate, normalized_code):
            return True
    return False

def get_totp_uri(username, secret):
    issuer = 'Bolder Electric'
    label = quote(f'{issuer}:{username}')
    return f'otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30'

def render_login(**kwargs):
    return render_template(
        'login.html',
        error=kwargs.get('error'),
        success=kwargs.get('success'),
        two_factor_required=kwargs.get('two_factor_required', False),
        two_factor_setup=kwargs.get('two_factor_setup', False),
        username=kwargs.get('username', ''),
        setup_secret=kwargs.get('setup_secret', ''),
        setup_uri=kwargs.get('setup_uri', '')
    )

def send_contact_email(name, email, phone, service_type, message):
    """Send contact form submission email using local postfix"""
    try:
        # Get the recipient email from database
        contact_info = db.get_contact_info()
        recipient_email = contact_info[1] if contact_info else 'info@bolderelectric.com'
        
        # Create email content
        subject = f"New Contact Form Submission - {service_type}"
        
        body = f"""
New Contact Form Submission from Bolder Electric Website

Name: {name}
Email: {email}
Phone: {phone}
Service Type: {service_type}

Message:
{message}

---
This email was sent from the Bolder Electric contact form.
"""
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"Bolder Electric Website <noreply@bolderelectric.com>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email using local postfix (much simpler)
        server = smtplib.SMTP('localhost')
        server.send_message(msg)
        server.quit()
        
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_booking_notification_email(booking_data, service_name):
    """Send booking notification email using local postfix."""
    try:
        recipient_email = 'info@bolderelectric.com'
        subject = f"New Booking Request - {service_name or 'Service'}"
        body = f"""
New Booking Request from Bolder Electric Website

Service: {service_name or booking_data.get('service_id')}
Customer Name: {booking_data.get('customer_name')}
Customer Email: {booking_data.get('customer_email')}
Customer Phone: {booking_data.get('customer_phone')}
Service Address: {booking_data.get('customer_address')}
Service Date: {booking_data.get('service_date')}
Time Slot: {booking_data.get('time_slot')}
Estimated Price: ${booking_data.get('total_price')}

Project Details:
{booking_data.get('description') or 'N/A'}

---
This email was sent from the Bolder Electric booking form.
"""

        msg = MIMEMultipart()
        msg['From'] = "Bolder Electric Website <noreply@bolderelectric.com>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('localhost')
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending booking email: {e}")
        return False

@app.route('/')
def home():
    # Get contact info for display
    contact_info = db.get_contact_info()
    contact_data = {
        'phone': '(951) 397-4025',
        'address': '30019 Buck Tail Drive, Menifee, CA 92587',
        'email': 'info@bolderelectric.com',
        'service_area': 'Riverside County & Surrounding Areas',
        'business_hours': 'Mon-Fri: 8AM-6PM, Emergency: 24/7'
    }
    
    if contact_info:
        contact_data = {
            'phone': contact_info[0],
            'email': contact_info[1], 
            'address': contact_info[2],
            'service_area': contact_info[3],
            'business_hours': contact_info[4]
        }
    
    return render_template('index.html', contact=contact_data)

@app.route('/gallery')
def gallery():
    photos = db.get_gallery_photos()
    return render_template('gallery.html', photos=photos)

@app.route('/commercial')
def commercial():
    return render_template('commercial.html')

@app.route('/residential')
def residential():
    return render_template('residential.html')

@app.route('/contact-submit', methods=['POST'])
def contact_submit():
    """Handle contact form submission"""
    try:
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        service_type = request.form.get('service_type')
        message = request.form.get('message')
        
        # Validate required fields
        if not all([name, email, phone, service_type, message]):
            return jsonify({
                'success': False,
                'message': 'Please fill out all required fields.'
            }), 400

        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')

        # Store submission in database
        db.add_contact_submission(name, email, phone, service_type, message, ip_address, user_agent)

        # Send email notification
        email_sent = send_contact_email(name, email, phone, service_type, message)

        if email_sent:
            return jsonify({
                'success': True,
                'message': 'Thank you for your inquiry! We will contact you soon.'
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Thank you. We received your inquiry and will contact you soon.'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'An error occurred. Please try again or call us directly.'
        }), 500

@app.route('/admin/gallery')
@admin_required
def admin_gallery():
    """Redirect legacy gallery admin route to the gallery tab in admin panel"""
    return redirect(url_for('admin', tab='gallery'))

@app.route('/admin/upload-photo', methods=['POST'])
@admin_required
def upload_photo():
    """Upload a new photo to gallery"""
    try:
        if 'PIL_AVAILABLE' not in globals() or not globals()['PIL_AVAILABLE']:
            return jsonify({
                'success': False,
                'message': 'Image processing not available. Please install Pillow.'
            }), 500
            
        if 'photo' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No photo file selected'
            }), 400
        
        file = request.files['photo']
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No photo file selected'
            }), 400
        
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{uuid4().hex[:10]}{ext.lower()}"
            file_path = os.path.join('static/images/gallery', filename)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save file
            file.save(file_path)
            
            # Add to database
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            category = request.form.get('category', 'general')
            
            photo_id = db.add_gallery_photo(filename, title, description, category)
            
            return jsonify({
                'success': True,
                'message': 'Photo uploaded successfully',
                'photo_id': photo_id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'File type not allowed'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error uploading photo: {str(e)}'
        }), 500

@app.route('/admin/update-photo/<int:photo_id>', methods=['POST'])
@admin_required
def update_photo(photo_id):
    """Update photo information"""
    try:
        data = request.get_json() or {}
        title = data.get('title', '')
        description = data.get('description', '')
        category = data.get('category', 'general')
        display_order = data.get('display_order')
        
        db.update_gallery_photo(photo_id, title, description, category, display_order)
        
        return jsonify({
            'success': True,
            'message': 'Photo updated successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error updating photo: {str(e)}'
        }), 500

@app.route('/admin/delete-photo/<int:photo_id>', methods=['POST'])
@admin_required
def delete_photo(photo_id):
    """Delete a photo from gallery"""
    try:
        db.delete_gallery_photo(photo_id)
        return jsonify({
            'success': True,
            'message': 'Photo deleted successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error deleting photo: {str(e)}'
        }), 500

@app.route('/admin/reorder-photos', methods=['POST'])
@admin_required
def reorder_photos():
    """Reorder photos in gallery"""
    try:
        photo_orders = request.get_json() or {}
        normalized_orders = []

        if isinstance(photo_orders, dict):
            normalized_orders = [
                (int(photo_id), int(order))
                for photo_id, order in photo_orders.items()
            ]
        elif isinstance(photo_orders, list):
            for item in photo_orders:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    normalized_orders.append((int(item[0]), int(item[1])))
                elif isinstance(item, dict) and 'id' in item and 'order' in item:
                    normalized_orders.append((int(item['id']), int(item['order'])))

        db.update_photo_order(normalized_orders)
        
        return jsonify({
            'success': True,
            'message': 'Photos reordered successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error reordering photos: {str(e)}'
        }), 500

def allowed_file(filename):
    """Check if file is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/schedule')
def schedule():
    services = db.get_services()
    time_slots = db.get_time_slots()
    # Convert tuples to dictionaries for template
    services_dict = [{
        'id': s[0],
        'name': s[1],
        'description': s[2],
        'base_price': s[3]
    } for s in services]
    time_slots_dict = [{
        'id': ts[0],
        'time_slot': ts[1]
    } for ts in time_slots]
    return render_template('schedule.html', services=services_dict, time_slots=time_slots_dict)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        step = request.form.get('step', 'password')
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')

        if step == 'verify_2fa':
            pending = session.get('pending_2fa')
            if not pending:
                return render_login(error='Two-factor session expired. Please log in again.')

            code = request.form.get('two_factor_code', '')
            username = pending.get('username', '')
            setup_mode = bool(pending.get('setup'))
            secret = session.get('pending_2fa_secret') if setup_mode else pending.get('two_factor_secret')

            if not verify_totp_code(secret, code):
                db.log_access(username, ip_address, user_agent, 'login_2fa_failed', False)
                return render_login(
                    error='Invalid authentication code.',
                    two_factor_required=True,
                    two_factor_setup=setup_mode,
                    username=username,
                    setup_secret=session.get('pending_2fa_secret', ''),
                    setup_uri=get_totp_uri(username, session.get('pending_2fa_secret', '')) if setup_mode else ''
                )

            user_id = pending.get('id')
            role = pending.get('role', 'admin')

            if setup_mode:
                db.set_user_two_factor(user_id, secret, True)
                db.log_access(username, ip_address, user_agent, 'login_2fa_setup', True)

            db.log_access(username, ip_address, user_agent, 'login_2fa_success', True)
            db.record_login_success(user_id, username, ip_address, user_agent)

            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['user_role'] = role or 'admin'
            session.pop('pending_2fa', None)
            session.pop('pending_2fa_secret', None)
            return redirect(url_for('admin'))

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        success, message, user = db.verify_login_password(username, password, ip_address, user_agent)

        if not success:
            return render_login(error=message, username=username)

        pending = {
            'id': user['id'],
            'username': user['username'],
            'role': user['role']
        }
        has_2fa = bool(user.get('two_factor_enabled')) and bool(user.get('two_factor_secret'))

        if has_2fa:
            pending['setup'] = False
            pending['two_factor_secret'] = user.get('two_factor_secret')
            session['pending_2fa'] = pending
            session.pop('pending_2fa_secret', None)
            return render_login(two_factor_required=True, username=username)

        setup_secret = generate_totp_secret()
        pending['setup'] = True
        session['pending_2fa'] = pending
        session['pending_2fa_secret'] = setup_secret
        return render_login(
            two_factor_required=True,
            two_factor_setup=True,
            username=username,
            setup_secret=setup_secret,
            setup_uri=get_totp_uri(username, setup_secret)
        )

    session.pop('pending_2fa', None)
    session.pop('pending_2fa_secret', None)
    return render_login()

@app.route('/logout')
def logout():
    # Log the logout
    if 'admin_username' in session:
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        db.log_access(session['admin_username'], ip_address, user_agent, 'logout', True)
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html', current_user=session.get('admin_username'), current_role=session.get('user_role', 'admin'))

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Verify current password
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        success, _, _ = db.verify_admin_login(session['admin_username'], current_password, ip_address, user_agent)
        
        if not success:
            return render_template('account.html', error='Current password is incorrect')
        
        if new_password != confirm_password:
            return render_template('account.html', error='New passwords do not match')
        
        # Update password
        db.update_admin_password(session['admin_username'], new_password)
        db.log_access(session['admin_username'], ip_address, user_agent, 'password_changed', True)
        
        return render_template('account.html', success='Password updated successfully')
    
    # Get recent login logs
    recent_logs = db.get_access_logs(5)
    
    return render_template('account.html', current_user=session['admin_username'], recent_logs=recent_logs)

# API Routes
@app.route('/api/services', methods=['GET'])
@admin_required
def get_services():
    services = db.get_services()
    return jsonify([{
        'id': s[0],
        'name': s[1],
        'description': s[2],
        'base_price': s[3]
    } for s in services])

@app.route('/api/services', methods=['POST'])
@admin_required
def add_service():
    data = request.get_json()
    service_id = db.add_service(
        data['name'],
        data['description'],
        data['base_price']
    )
    return jsonify({'success': True, 'id': service_id})

@app.route('/api/services/<int:service_id>', methods=['PUT'])
@admin_required
def update_service(service_id):
    data = request.get_json()
    db.update_service(
        service_id,
        data['name'],
        data['description'],
        data['base_price']
    )
    return jsonify({'success': True})

@app.route('/api/services/<int:service_id>', methods=['DELETE'])
@admin_required
def delete_service(service_id):
    db.delete_service(service_id)
    return jsonify({'success': True})

@app.route('/api/time-slots', methods=['GET'])
@admin_required
def get_time_slots():
    time_slots = db.get_time_slots()
    return jsonify([{
        'id': ts[0],
        'time_slot': ts[1]
    } for ts in time_slots])

@app.route('/api/availability/<date>', methods=['GET'])
@admin_required
def get_availability(date):
    availability = db.get_availability(date)
    return jsonify([{
        'time_slot_id': a[0],
        'time_slot': a[1],
        'is_available': bool(a[2]) if a[2] is not None else True
    } for a in availability])

@app.route('/api/availability', methods=['POST'])
@admin_required
def set_availability():
    data = request.get_json()
    db.set_availability(
        data['date'],
        data['time_slot_id'],
        data['is_available']
    )
    return jsonify({'success': True})

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.get_json()
    booking_id = db.add_booking(
        data['service_id'],
        data['customer_name'],
        data['customer_phone'],
        data['customer_email'],
        data['customer_address'],
        data['service_date'],
        data['time_slot'],
        data['description'],
        data['total_price']
    )
    service = db.get_service_by_id(data['service_id'])
    service_name = service[1] if service else 'Unknown Service'
    email_sent = send_booking_notification_email(data, service_name)
    return jsonify({
        'success': True,
        'booking_id': booking_id,
        'notification_sent': email_sent
    })

@app.route('/api/bookings', methods=['GET'])
@login_required
def get_bookings():
    bookings = db.get_bookings()
    return jsonify([{
        'id': b[0],
        'service_id': b[1],
        'customer_name': b[2],
        'customer_phone': b[3],
        'customer_email': b[4],
        'customer_address': b[5],
        'service_date': b[6],
        'time_slot': b[7],
        'description': b[8],
        'total_price': b[9],
        'status': b[10],
        'service_name': b[11]
    } for b in bookings])

@app.route('/api/contact', methods=['GET'])
@admin_required
def get_contact():
    contact = db.get_contact_info()
    if contact:
        return jsonify({
            'phone': contact[0],
            'email': contact[1],
            'address': contact[2],
            'service_area': contact[3],
            'business_hours': contact[4]
        })
    else:
        return jsonify({
            'phone': '(951) 397-4025',
            'email': 'info@bolderelectric.com',
            'address': '30019 Buck Tail Drive, Menifee, CA 92587',
            'service_area': 'Riverside County & Surrounding Areas',
            'business_hours': 'Mon-Fri: 8AM-6PM, Emergency: 24/7'
        })

@app.route('/api/contact', methods=['POST'])
@admin_required
def update_contact():
    data = request.get_json()
    db.update_contact_info(
        data['phone'],
        data['email'],
        data['address'],
        data['service_area'],
        data['business_hours']
    )
    return jsonify({'success': True})

@app.route('/api/logs', methods=['GET'])
@admin_required
def get_logs():
    logs = db.get_access_logs(100)
    return jsonify([{
        'username': log[0],
        'ip_address': log[1],
        'action': log[2],
        'success': log[3],
        'timestamp': log[4]
    } for log in logs])

@app.route('/api/gallery-photos', methods=['GET'])
@admin_required
def get_gallery_photos():
    photos = db.get_gallery_photos()
    return jsonify([{
        'id': p[0],
        'filename': p[1],
        'title': p[2],
        'description': p[3],
        'category': p[4],
        'display_order': p[5]
    } for p in photos])

@app.route('/api/contact-submissions', methods=['GET'])
@login_required
def get_contact_submissions():
    submissions = db.get_contact_submissions(300)
    return jsonify([{
        'id': s[0],
        'name': s[1],
        'email': s[2],
        'phone': s[3],
        'service_type': s[4],
        'message': s[5],
        'ip_address': s[6],
        'user_agent': s[7],
        'created_at': s[8]
    } for s in submissions])

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    users = db.get_users()
    return jsonify([{
        'id': u[0],
        'username': u[1],
        'role': u[2],
        'is_active': bool(u[3]),
        'created_at': u[4],
        'last_login': u[5],
        'two_factor_enabled': bool(u[6])
    } for u in users])

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = (data.get('role') or 'viewer').strip().lower()
    if role not in ('admin', 'editor', 'viewer'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    if not username or len(password) < 8:
        return jsonify({'success': False, 'message': 'Username and password (min 8 chars) required'}), 400
    if db.get_user_by_username(username):
        return jsonify({'success': False, 'message': 'Username already exists'}), 400
    try:
        db.create_user(username, password, role)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def update_user_role(user_id):
    data = request.get_json() or {}
    role = (data.get('role') or '').strip().lower()
    if role not in ('admin', 'editor', 'viewer'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    db.update_user_role(user_id, role)
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>/password', methods=['PUT'])
@admin_required
def reset_user_password(user_id):
    data = request.get_json() or {}
    password = data.get('password') or ''
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
    db.update_user_password(user_id, password)
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>/active', methods=['PUT'])
@admin_required
def set_user_active(user_id):
    current_user = db.get_user_by_username(session.get('admin_username'))
    if current_user and current_user[0] == user_id:
        return jsonify({'success': False, 'message': 'You cannot deactivate your own account'}), 400
    data = request.get_json() or {}
    is_active = bool(data.get('is_active'))
    db.set_user_active(user_id, is_active)
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>/reset-2fa', methods=['PUT'])
@admin_required
def reset_user_two_factor(user_id):
    db.clear_user_two_factor(user_id)
    return jsonify({'success': True})

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('static', 'sitemap.xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/images', 'favicon.ico')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
