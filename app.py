from flask import Flask, render_template, request, send_from_directory, jsonify, session, redirect, url_for, Response
from flask_compress import Compress
import os
import base64
import io
import hashlib
import hmac
import struct
import time
import secrets
from datetime import datetime, timedelta
from collections import defaultdict, deque
from database import DatabaseManager
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from uuid import uuid4
from urllib.parse import quote
try:
    import qrcode
    QRCODE_AVAILABLE = True
except Exception:
    qrcode = None
    QRCODE_AVAILABLE = False

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

def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _build_secret_key():
    configured = (os.environ.get('SECRET_KEY') or '').strip()
    if configured:
        return configured
    fallback = base64.urlsafe_b64encode(os.urandom(48)).decode('ascii')
    print('WARNING: SECRET_KEY is not set. Using a temporary runtime key; sessions will reset on restart.')
    return fallback


app = Flask(__name__)
app.secret_key = _build_secret_key()
flask_env = (os.environ.get('FLASK_ENV') or '').strip().lower()
is_production = flask_env in ('production', 'prod')
force_https = _env_bool('FORCE_HTTPS', False)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=_env_bool('SESSION_COOKIE_SECURE', force_https),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=max(1, int(os.environ.get('SESSION_LIFETIME_HOURS', '12'))))
)

try:
    MAX_UPLOAD_MB = max(1, int(os.environ.get('MAX_UPLOAD_MB', '25')))
except ValueError:
    MAX_UPLOAD_MB = 25
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024
Compress(app)
db = DatabaseManager()

RATE_LIMIT_RULES = (
    {'name': 'login', 'path': '/login', 'methods': {'POST'}, 'limit': 12, 'window': 300, 'prefix': False},
    {'name': 'contact', 'path': '/contact-submit', 'methods': {'POST'}, 'limit': 20, 'window': 3600, 'prefix': False},
    {'name': 'booking_submit', 'path': '/api/bookings', 'methods': {'POST'}, 'limit': 40, 'window': 3600, 'prefix': False},
    {'name': 'api_mutation', 'path': '/api/', 'methods': {'POST', 'PUT', 'DELETE', 'PATCH'}, 'limit': 240, 'window': 300, 'prefix': True},
    {'name': 'admin_upload', 'path': '/admin/upload-photo', 'methods': {'POST'}, 'limit': 50, 'window': 300, 'prefix': False},
)
_rate_buckets = defaultdict(deque)


def get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.context_processor
def inject_security_template_values():
    return {
        'csrf_token': get_csrf_token
    }


def _is_secure_request():
    proto = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
    return request.is_secure or proto == 'https'


def _extract_csrf_token_from_request():
    token = request.headers.get('X-CSRF-Token', '').strip()
    if token:
        return token
    token = request.form.get('csrf_token', '').strip()
    if token:
        return token
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return (data.get('csrf_token') or '').strip()
    return ''


def _csrf_failure_response():
    message = 'Invalid or missing CSRF token. Refresh the page and try again.'
    if request.path.startswith('/api/') or request.path.startswith('/contact-submit') or request.path.startswith('/admin/'):
        return jsonify({'success': False, 'message': message}), 400
    return message, 400


def _rate_limit_failure_response():
    message = 'Too many requests. Please wait a moment and try again.'
    if request.path.startswith('/api/') or request.path.startswith('/contact-submit') or request.path.startswith('/admin/'):
        return jsonify({'success': False, 'message': message}), 429
    return message, 429


def _rate_key(scope):
    ip = get_client_ip() or 'unknown'
    username = session.get('admin_username') or 'anon'
    return f'{scope}:{ip}:{username}'


def _is_rate_limited(scope, limit, window):
    now = time.time()
    key = _rate_key(scope)
    bucket = _rate_buckets[key]
    threshold = now - window
    while bucket and bucket[0] < threshold:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@app.before_request
def security_guardrails():
    host = (request.host or '').split(':')[0].lower()
    localhost_hosts = {'127.0.0.1', 'localhost'}

    if force_https and not _is_secure_request() and host not in localhost_hosts:
        https_url = request.url.replace('http://', 'https://', 1)
        return redirect(https_url, code=301)

    for rule in RATE_LIMIT_RULES:
        path_match = request.path.startswith(rule['path']) if rule['prefix'] else request.path == rule['path']
        if path_match and request.method in rule['methods']:
            if _is_rate_limited(rule['name'], rule['limit'], rule['window']):
                return _rate_limit_failure_response()
            break

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        expected = session.get('_csrf_token') or get_csrf_token()
        provided = _extract_csrf_token_from_request()
        if not provided or not hmac.compare_digest(provided, expected):
            return _csrf_failure_response()


# Optional noindex header (enabled only when BLOCK_INDEXING=true)
@app.after_request
def add_security_headers(response):
    sensitive_paths = (
        '/admin',
        '/login',
        '/account',
        '/api/'
    )
    if request.path.startswith(sensitive_paths):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
    elif os.environ.get('BLOCK_INDEXING', '').lower() in ('1', 'true', 'yes'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, nosnippet, noarchive, notranslate, noimageindex'

    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'geolocation=(), camera=(), microphone=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data: https: blob:; "
        "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "font-src 'self' data: https://cdnjs.cloudflare.com; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com https://analytics.google.com; media-src 'self' data: blob:; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    if _is_secure_request():
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

    return response

@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error):
    message = f'File is too large. Maximum upload size is {MAX_UPLOAD_MB}MB.'
    if request.path.startswith('/admin/upload-photo'):
        return jsonify({'success': False, 'message': message}), 413
    return jsonify({'success': False, 'message': message}), 413

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

def can_manage_bookings():
    return session.get('admin_logged_in') and session.get('user_role') in ('admin', 'editor')

def get_client_ip():
    """Get client IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def _send_email(to_email, subject, body):
    """Send email via configured SMTP provider, with localhost fallback."""
    try:
        smtp_host = os.environ.get('SMTP_HOST', '').strip()
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        smtp_use_tls = _env_bool('SMTP_USE_TLS', True)
        smtp_use_ssl = _env_bool('SMTP_USE_SSL', False)
        smtp_timeout = int(os.environ.get('SMTP_TIMEOUT', '15'))

        from_email = os.environ.get('SMTP_FROM_EMAIL', '').strip() or smtp_username or 'noreply@bolderelectric.com'
        from_name = os.environ.get('SMTP_FROM_NAME', 'Bolder Electric Website').strip()
        from_header = f"{from_name} <{from_email}>"

        msg = MIMEMultipart()
        msg['From'] = from_header
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if smtp_host:
            if smtp_use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=smtp_timeout)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
                server.ehlo()
                if smtp_use_tls:
                    server.starttls()
                    server.ehlo()

            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
        else:
            # Backward-compatible fallback for environments with local postfix.
            server = smtplib.SMTP('localhost')

        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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

def build_qr_data_uri(text):
    """Build PNG QR code as a data URI for inline rendering."""
    if not QRCODE_AVAILABLE or not text:
        return ''
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    output = io.BytesIO()
    image.save(output, format='PNG')
    encoded = base64.b64encode(output.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'

def render_login(**kwargs):
    return render_template(
        'login.html',
        error=kwargs.get('error'),
        success=kwargs.get('success'),
        two_factor_required=kwargs.get('two_factor_required', False),
        two_factor_setup=kwargs.get('two_factor_setup', False),
        username=kwargs.get('username', ''),
        setup_secret=kwargs.get('setup_secret', ''),
        setup_uri=kwargs.get('setup_uri', ''),
        setup_qr=kwargs.get('setup_qr', '')
    )

def send_contact_email(name, email, phone, service_type, message):
    """Send contact form submission email."""
    try:
        # Get the recipient email from settings/database.
        contact_info = db.get_contact_info()
        fallback_email = contact_info[1] if contact_info else 'support@bolderelectric.com'
        recipient_email = db.get_site_setting('contact_notification_email', fallback_email)
        if not recipient_email:
            recipient_email = fallback_email
        
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
        
        return _send_email(recipient_email, subject, body)
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_booking_notification_email(booking_data, service_name):
    """Send booking notification email."""
    try:
        env_fallback = os.environ.get('BOOKING_NOTIFICATION_EMAIL', 'info@bolderelectric.com')
        recipient_email = db.get_site_setting('booking_notification_email', env_fallback)
        if not recipient_email:
            recipient_email = env_fallback
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

        return _send_email(recipient_email, subject, body)
    except Exception as e:
        print(f"Error sending booking email: {e}")
        return False

def send_booking_status_email(booking, status, admin_note=''):
    """Notify customer when booking is confirmed/rejected."""
    try:
        recipient_email = booking.get('customer_email')
        if not recipient_email:
            return False

        status_label = (status or '').strip().lower()
        if status_label == 'confirmed':
            subject = "Booking Confirmed - Bolder Electric"
            intro = "Good news - your booking has been confirmed."
        elif status_label == 'rejected':
            subject = "Booking Update - Bolder Electric"
            intro = "Thank you for your request. We are unable to confirm the selected slot."
        else:
            subject = "Booking Status Update - Bolder Electric"
            intro = f"Your booking status has been updated to: {status_label}."

        body = f"""
{intro}

Service: {booking.get('service_name') or 'Service'}
Date: {booking.get('service_date')}
Time: {booking.get('time_slot')}
Name: {booking.get('customer_name')}
Phone: {booking.get('customer_phone')}
Address: {booking.get('customer_address')}

"""
        if admin_note:
            body += f"Note from our team:\n{admin_note}\n\n"

        body += """If you have any questions, please reply to this email or call us at (951) 397-4025.

Thank you,
Bolder Electric
"""

        return _send_email(recipient_email, subject, body)
    except Exception as e:
        print(f"Error sending booking status email: {e}")
        return False

@app.route('/')
def home():
    # Get contact info for display
    contact_info = db.get_contact_info()
    contact_data = {
        'phone': '(951) 397-4025',
        'address': '30019 Buck Tail Drive, Menifee, CA 92587',
        'email': 'support@bolderelectric.com',
        'service_area': 'Riverside County & Southern California',
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
    
    services = db.get_services()
    service_descriptions = {
        'commercial': '',
        'residential': '',
        'emergency': '',
        'lighting': '',
        'panel': '',
        'safety': ''
    }
    service_prices = {
        'commercial': None,
        'residential': None,
        'emergency': None,
        'lighting': None,
        'panel': None,
        'safety': None
    }

    # Stable defaults for seeded records, if IDs are still aligned.
    id_map = {
        1: 'commercial',
        2: 'residential',
        3: 'emergency',
        4: 'panel',
        5: 'lighting'
    }

    for service in services:
        service_id = service[0]
        description = (service[2] or '').strip()
        base_price = service[3]
        key = id_map.get(service_id)
        if key and description and not service_descriptions.get(key):
            service_descriptions[key] = description
        if key and base_price is not None and service_prices.get(key) is None:
            service_prices[key] = float(base_price)

    # Name-based fallback so edited/reordered services still map correctly.
    for service in services:
        name = (service[1] or '').strip().lower()
        description = (service[2] or '').strip()
        base_price = service[3]
        if not description:
            description = ''

        if 'commercial' in name:
            if description:
                service_descriptions['commercial'] = description
            service_prices['commercial'] = float(base_price) if base_price is not None else service_prices['commercial']
        elif 'residential' in name:
            if description:
                service_descriptions['residential'] = description
            service_prices['residential'] = float(base_price) if base_price is not None else service_prices['residential']
        elif 'emergency' in name:
            if description:
                service_descriptions['emergency'] = description
            service_prices['emergency'] = float(base_price) if base_price is not None else service_prices['emergency']
        elif 'lighting' in name:
            if description:
                service_descriptions['lighting'] = description
            service_prices['lighting'] = float(base_price) if base_price is not None else service_prices['lighting']
        elif 'panel' in name:
            if description:
                service_descriptions['panel'] = description
            service_prices['panel'] = float(base_price) if base_price is not None else service_prices['panel']
        elif 'safety' in name or 'inspection' in name:
            if description:
                service_descriptions['safety'] = description
            service_prices['safety'] = float(base_price) if base_price is not None else service_prices['safety']
    
    top_reviews = db.get_top_reviews(5)

    review_links = {
        'google': os.environ.get('REVIEW_URL_GOOGLE', 'https://www.google.com/search?q=Bolder+Electric+Menifee+CA'),
        'yelp': os.environ.get('REVIEW_URL_YELP', 'https://www.yelp.com/search?find_desc=Bolder+Electric&find_loc=Menifee%2C+CA'),
        'facebook': os.environ.get('REVIEW_URL_FACEBOOK', 'https://www.facebook.com/')
    }

    return render_template(
        'index.html',
        contact=contact_data,
        service_descriptions=service_descriptions,
        service_prices=service_prices,
        top_reviews=top_reviews,
        review_links=review_links
    )

@app.route('/gallery')
def gallery():
    photos = db.get_gallery_photos()
    return render_template('gallery.html', photos=photos)

@app.route('/commercial')
def commercial():
    return redirect(url_for('home') + '#services')

@app.route('/residential')
def residential():
    return redirect(url_for('home') + '#services')

@app.route('/about')
def about():
    return redirect(url_for('home') + '#about')

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


@app.route('/api/reviews', methods=['POST'])
def submit_review():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        source = (data.get('source') or 'website').strip().lower()
        review_text = (data.get('review_text') or '').strip()
        rating_raw = data.get('rating')

        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            rating = 0

        valid_sources = {'website', 'google', 'yelp', 'facebook'}
        if source not in valid_sources:
            source = 'website'

        if len(name) < 2 or len(review_text) < 15 or rating < 1 or rating > 5:
            return jsonify({'success': False, 'message': 'Please provide name, a review (15+ chars), and a rating from 1-5.'}), 400

        db.add_review(name, rating, source, review_text, is_featured=True)
        return jsonify({'success': True, 'message': 'Thank you for your review.'})
    except Exception:
        return jsonify({'success': False, 'message': 'Could not submit your review right now. Please try again.'}), 500

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
            
            # Save optimized image when possible to keep gallery fast.
            try:
                max_dim = int(os.environ.get('MAX_GALLERY_IMAGE_DIM', '2200'))
            except ValueError:
                max_dim = 2200
            try:
                jpg_quality = int(os.environ.get('GALLERY_JPEG_QUALITY', '82'))
            except ValueError:
                jpg_quality = 82
            jpg_quality = max(60, min(90, jpg_quality))

            saved = False
            try:
                image = Image.open(file.stream)
                resampling = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                image.thumbnail((max_dim, max_dim), resampling)

                if ext.lower() in ('.jpg', '.jpeg'):
                    if image.mode not in ('RGB', 'L'):
                        image = image.convert('RGB')
                    image.save(file_path, format='JPEG', quality=jpg_quality, optimize=True, progressive=True)
                elif ext.lower() == '.webp':
                    if image.mode not in ('RGB', 'L'):
                        image = image.convert('RGB')
                    image.save(file_path, format='WEBP', quality=80, method=6)
                elif ext.lower() == '.png':
                    image.save(file_path, format='PNG', optimize=True)
                else:
                    file.stream.seek(0)
                    file.save(file_path)
                saved = True
            except Exception:
                # Fallback to original upload if optimization fails.
                try:
                    file.stream.seek(0)
                except Exception:
                    pass
                file.save(file_path)
                saved = True

            if not saved:
                return jsonify({
                    'success': False,
                    'message': 'Unable to save uploaded image'
                }), 500
            
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

@app.route('/booking-confirmation')
def booking_confirmation():
    return render_template('booking_confirmation.html')

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
                    setup_uri=get_totp_uri(username, session.get('pending_2fa_secret', '')) if setup_mode else '',
                    setup_qr=build_qr_data_uri(get_totp_uri(username, session.get('pending_2fa_secret', ''))) if setup_mode else ''
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
            setup_uri=get_totp_uri(username, setup_secret),
            setup_qr=build_qr_data_uri(get_totp_uri(username, setup_secret))
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

@app.route('/api/bookings/<int:booking_id>/status', methods=['PUT'])
@login_required
def update_booking_status(booking_id):
    if not can_manage_bookings():
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403

    data = request.get_json() or {}
    status = (data.get('status') or '').strip().lower()
    admin_note = (data.get('note') or '').strip()
    if status not in ('pending', 'confirmed', 'rejected', 'completed'):
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    booking_row = db.get_booking_by_id(booking_id)
    if not booking_row:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    db.update_booking_status(booking_id, status)

    booking_dict = {
        'id': booking_row[0],
        'service_id': booking_row[1],
        'customer_name': booking_row[2],
        'customer_phone': booking_row[3],
        'customer_email': booking_row[4],
        'customer_address': booking_row[5],
        'service_date': booking_row[6],
        'time_slot': booking_row[7],
        'description': booking_row[8],
        'total_price': booking_row[9],
        'status': status,
        'service_name': booking_row[11]
    }
    email_sent = send_booking_status_email(booking_dict, status, admin_note)

    return jsonify({
        'success': True,
        'email_sent': email_sent
    })

@app.route('/api/bookings/<int:booking_id>', methods=['PUT'])
@login_required
def update_booking(booking_id):
    if not can_manage_bookings():
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403

    booking_row = db.get_booking_by_id(booking_id)
    if not booking_row:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    data = request.get_json() or {}
    customer_name = (data.get('customer_name') or '').strip()
    customer_phone = (data.get('customer_phone') or '').strip()
    customer_email = (data.get('customer_email') or '').strip()
    customer_address = (data.get('customer_address') or '').strip()
    service_date = (data.get('service_date') or '').strip()
    time_slot = (data.get('time_slot') or '').strip()
    description = (data.get('description') or '').strip()
    total_price = data.get('total_price')

    if not all([customer_name, customer_phone, customer_email, customer_address, service_date, time_slot]):
        return jsonify({'success': False, 'message': 'Missing required booking fields'}), 400

    try:
        total_price = float(total_price)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid price value'}), 400

    db.update_booking(
        booking_id,
        customer_name,
        customer_phone,
        customer_email,
        customer_address,
        service_date,
        time_slot,
        description,
        total_price
    )
    return jsonify({'success': True})

@app.route('/api/bookings/<int:booking_id>', methods=['DELETE'])
@login_required
def delete_booking(booking_id):
    if not can_manage_bookings():
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403

    booking_row = db.get_booking_by_id(booking_id)
    if not booking_row:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    db.delete_booking(booking_id)
    return jsonify({'success': True})

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
            'email': 'support@bolderelectric.com',
            'address': '30019 Buck Tail Drive, Menifee, CA 92587',
            'service_area': 'Riverside County & Southern California',
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


@app.route('/api/settings/notifications', methods=['GET'])
@admin_required
def get_notification_settings():
    contact_info = db.get_contact_info()
    contact_fallback = contact_info[1] if contact_info else 'support@bolderelectric.com'
    booking_fallback = os.environ.get('BOOKING_NOTIFICATION_EMAIL', 'info@bolderelectric.com')
    return jsonify({
        'contact_notification_email': db.get_site_setting('contact_notification_email', contact_fallback),
        'booking_notification_email': db.get_site_setting('booking_notification_email', booking_fallback)
    })


@app.route('/api/settings/notifications', methods=['POST'])
@admin_required
def update_notification_settings():
    data = request.get_json() or {}
    contact_notification_email = (data.get('contact_notification_email') or '').strip()
    booking_notification_email = (data.get('booking_notification_email') or '').strip()

    if not contact_notification_email or '@' not in contact_notification_email:
        return jsonify({'success': False, 'message': 'Valid contact notification email is required'}), 400
    if not booking_notification_email or '@' not in booking_notification_email:
        return jsonify({'success': False, 'message': 'Valid booking notification email is required'}), 400

    db.set_site_setting('contact_notification_email', contact_notification_email)
    db.set_site_setting('booking_notification_email', booking_notification_email)
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
        'acknowledged': bool(s[8]),
        'acknowledged_at': s[9],
        'created_at': s[10]
    } for s in submissions])


@app.route('/api/contact-submissions/<int:submission_id>/acknowledge', methods=['PUT'])
@login_required
def acknowledge_contact_submission(submission_id):
    if not can_manage_bookings():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    updated = db.acknowledge_contact_submission(submission_id)
    if not updated:
        return jsonify({'success': False, 'message': 'Submission not found'}), 404
    return jsonify({'success': True})


@app.route('/api/contact-submissions/<int:submission_id>', methods=['DELETE'])
@login_required
def delete_contact_submission(submission_id):
    if not can_manage_bookings():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    deleted = db.delete_contact_submission(submission_id)
    if not deleted:
        return jsonify({'success': False, 'message': 'Submission not found'}), 404
    return jsonify({'success': True})

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
    today = datetime.utcnow().date().isoformat()
    base_url = 'https://bolderelectric.com'
    entries = [
        ('/', 'weekly', '1.0'),
        ('/gallery', 'weekly', '0.9'),
        ('/schedule', 'weekly', '0.9'),
    ]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for path, changefreq, priority in entries:
        lines.extend([
            '  <url>',
            f'    <loc>{base_url}{path}</loc>',
            f'    <lastmod>{today}</lastmod>',
            f'    <changefreq>{changefreq}</changefreq>',
            f'    <priority>{priority}</priority>',
            '  </url>'
        ])
    lines.append('</urlset>')
    return Response('\n'.join(lines), mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/images', 'favicon.ico')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug_mode = _env_bool('FLASK_DEBUG', False)
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
