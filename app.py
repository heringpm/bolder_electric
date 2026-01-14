from flask import Flask, render_template, request, send_from_directory, jsonify, session, redirect, url_for
import os
from database import DatabaseManager
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this for production!
db = DatabaseManager()

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

@app.route('/commercial')
def commercial():
    return render_template('commercial.html')

@app.route('/residential')
def residential():
    return render_template('residential.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

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
