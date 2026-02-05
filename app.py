from flask import Flask, render_template, request, send_from_directory, jsonify, session, redirect, url_for
import os
from database import DatabaseManager
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
from PIL import Image
import sqlite3

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this for production!
db = DatabaseManager()

# Add noindex headers to prevent search engine indexing during development
@app.after_request
def add_noindex_headers(response):
    if not app.debug:  # Only in production
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, nosnippet, noarchive, notranslate, noimageindex'
    return response

# Initialize admin user if not exists
def init_admin():
    try:
        # Only create admin user if table doesn't exist
        conn = sqlite3.connect('bolder_electric.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_users'")
        if not cursor.fetchone():
            db.create_admin_user('admin', 'usLaG4wLCnJW1F')
        conn.close()
    except:
        pass  # Admin user already exists or other error

init_admin()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
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
    return render_template('gallery.html')

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
        
        # Send email
        email_sent = send_contact_email(name, email, phone, service_type, message)
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': 'Thank you for your inquiry! We will contact you soon.'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'There was an error sending your message. Please call us directly.'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'An error occurred. Please try again or call us directly.'
        }), 500

@app.route('/admin/gallery')
@admin_required
def admin_gallery():
    """Gallery management page"""
    photos = db.get_gallery_photos()
    return render_template('admin_gallery.html', photos=photos)

@app.route('/admin/upload-photo', methods=['POST'])
@admin_required
def upload_photo():
    """Upload a new photo to gallery"""
    try:
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
            filename = secure_filename(file.filename)
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
        data = request.get_json()
        title = data.get('title', '')
        description = data.get('description', '')
        category = data.get('category', 'general')
        
        db.update_gallery_photo(photo_id, title, description, category)
        
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
        photo_orders = request.get_json()
        db.update_photo_order(photo_orders)
        
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
        username = request.form['username']
        password = request.form['password']
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        
        success, message = db.verify_admin_login(username, password, ip_address, user_agent)
        
        if success:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error=message)
    
    return render_template('login.html')

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
@admin_required
def admin():
    return render_template('admin.html')

@app.route('/account', methods=['GET', 'POST'])
@admin_required
def account():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Verify current password
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        success, _ = db.verify_admin_login(session['admin_username'], current_password, ip_address, user_agent)
        
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
    return jsonify({'success': True, 'booking_id': booking_id})

@app.route('/api/bookings', methods=['GET'])
@admin_required
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

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('static', 'sitemap.xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
