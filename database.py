import sqlite3
import json
from datetime import datetime, timedelta
import hashlib
import secrets

class DatabaseManager:
    def __init__(self, db_path='bolder_electric.db'):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        return conn
    
    def init_database(self):
        """Initialize the database with required tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Admin users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    failed_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Access logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    action TEXT,
                    success BOOLEAN,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Contact info table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contact_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL,
                    address TEXT NOT NULL,
                    service_area TEXT NOT NULL,
                    business_hours TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Services table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    base_price REAL NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Time slots table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS time_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time_slot TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Availability table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS availability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    time_slot_id INTEGER,
                    is_available BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (time_slot_id) REFERENCES time_slots (id)
                )
            ''')
            
            # Bookings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id INTEGER,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    customer_address TEXT NOT NULL,
                    service_date DATE NOT NULL,
                    time_slot TEXT NOT NULL,
                    description TEXT,
                    total_price REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (service_id) REFERENCES services (id)
                )
            ''')
            
            # Gallery photos table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gallery_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    category TEXT DEFAULT 'general',
                    display_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            self.seed_default_data()
        except Exception as e:
            print(f"Database initialization error: {e}")
            raise
    
    def seed_default_data(self):
        """Seed default services and time slots"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Only seed if tables are empty
            cursor.execute("SELECT COUNT(*) FROM admin_users")
            admin_count = cursor.fetchone()[0]
            
            if admin_count == 0:
                # Create default admin user
                self.create_admin_user('admin', 'usLaG4wLCnJW1F')
                print("Created admin user")
            
            # Check if contact info exists
            cursor.execute("SELECT COUNT(*) FROM contact_info")
            if cursor.fetchone()[0] == 0:
                # Insert default contact info
                cursor.execute('''
                    INSERT INTO contact_info (phone, email, address, service_area, business_hours)
                    VALUES (?, ?, ?, ?, ?)
                ''', ('(951) 397-4025', 'info@bolderelectric.com', 
                      '30019 Buck Tail Drive, Menifee, CA 92587', 
                      'Riverside County & Surrounding Areas', 
                      'Mon-Fri: 8AM-6PM, Emergency: 24/7'))
                print("Created contact info")
            
            # Check if services already exist
            cursor.execute("SELECT COUNT(*) FROM services")
            if cursor.fetchone()[0] == 0:
                # Insert default services
                default_services = [
                    ('Commercial Electrical', 'Complete electrical solutions for businesses, offices, and commercial properties', 150.0),
                    ('Residential Electrical', 'Professional electrical services for homes, apartments, and residential complexes', 100.0),
                    ('Emergency Service', '24/7 emergency electrical repair services', 250.0),
                    ('Panel Upgrade', 'Electrical panel upgrades and replacements', 300.0),
                    ('Lighting Installation', 'Indoor and outdoor lighting installation services', 125.0)
                ]
                
                cursor.executemany('''
                    INSERT INTO services (name, description, base_price) 
                    VALUES (?, ?, ?)
                ''', default_services)
                print("Created default services")
            
            # Check if time slots already exist
            cursor.execute("SELECT COUNT(*) FROM time_slots")
            if cursor.fetchone()[0] == 0:
                # Insert default time slots
                default_time_slots = [
                    ('8:00 AM',), ('9:00 AM',), ('10:00 AM',), ('11:00 AM',),
                    ('12:00 PM',), ('1:00 PM',), ('2:00 PM',), ('3:00 PM',), ('4:00 PM',)
                ]
                
                cursor.executemany('''
                    INSERT INTO time_slots (time_slot) VALUES (?)
                ''', default_time_slots)
                print("Created time slots")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Seeding error: {e}")
            if conn:
                conn.close()
    
    def hash_password(self, password, salt=None):
        """Hash password with salt using SHA-256"""
        if salt is None:
            salt = secrets.token_hex(32)
        
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return password_hash, salt
    
    def create_admin_user(self, username, password):
        """Create admin user with hashed password"""
        password_hash, salt = self.hash_password(password)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admin_users (username, password_hash, salt)
            VALUES (?, ?, ?)
        ''', (username, password_hash, salt))
        conn.commit()
        conn.close()
    
    def verify_admin_login(self, username, password, ip_address, user_agent):
        """Verify admin login credentials with security checks"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Log the attempt
            success = False
            
            cursor.execute('''
                SELECT id, password_hash, salt, failed_attempts, locked_until, is_active
                FROM admin_users 
                WHERE username = ?
            ''', (username,))
            
            user = cursor.fetchone()
            
            if not user:
                self.log_access(username, ip_address, user_agent, 'login_attempt', False)
                return False, "Invalid credentials"
            
            user_id, stored_hash, salt, failed_attempts, locked_until, is_active = user
            
            # Check if account is locked
            if locked_until and datetime.fromisoformat(locked_until) > datetime.now():
                self.log_access(username, ip_address, user_agent, 'login_attempt_locked', False)
                return False, "Account locked due to too many failed attempts"
            
            # Check if account is active
            if not is_active:
                self.log_access(username, ip_address, user_agent, 'login_attempt_inactive', False)
                return False, "Account is disabled"
            
            # Verify password
            password_hash, _ = self.hash_password(password, salt)
            
            if password_hash == stored_hash:
                # Successful login - reset failed attempts
                cursor.execute('''
                    UPDATE admin_users 
                    SET failed_attempts = 0, last_login = CURRENT_TIMESTAMP, locked_until = NULL
                    WHERE id = ?
                ''', (user_id,))
                success = True
                self.log_access(username, ip_address, user_agent, 'login_success', True)
            else:
                # Failed login - increment failed attempts
                failed_attempts += 1
                cursor.execute('''
                    UPDATE admin_users 
                    SET failed_attempts = ?
                    WHERE id = ?
                ''', (failed_attempts, user_id))
                
                # Lock account after 5 failed attempts for 30 minutes
                if failed_attempts >= 5:
                    lock_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                    cursor.execute('''
                        UPDATE admin_users 
                        SET locked_until = ?
                        WHERE id = ?
                    ''', (lock_until, user_id))
                
                self.log_access(username, ip_address, user_agent, 'login_failed', False)
            
            conn.commit()
            
            if success:
                return True, "Login successful"
            else:
                return False, "Invalid credentials"
                
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            return False, f"Database error: {str(e)}"
        finally:
            if conn:
                conn.close()
    
    def log_access(self, username, ip_address, user_agent, action, success):
        """Log access attempts - simplified to avoid blocking"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO access_logs (username, ip_address, user_agent, action, success)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, ip_address, user_agent, action, success))
            conn.commit()
            conn.close()
        except sqlite3.Error:
            pass  # Don't fail if logging fails
    
    def get_access_logs(self, limit=100):
        """Get access logs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, ip_address, action, success, timestamp
            FROM access_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        logs = cursor.fetchall()
        conn.close()
        return logs
    
    def update_admin_password(self, username, new_password):
        """Update admin password"""
        password_hash, salt = self.hash_password(new_password)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE admin_users 
            SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL
            WHERE username = ?
        ''', (password_hash, salt, username))
        conn.commit()
        conn.close()
    
    def get_contact_info(self):
        """Get contact information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT phone, email, address, service_area, business_hours FROM contact_info LIMIT 1')
        contact = cursor.fetchone()
        conn.close()
        return contact
    
    def update_contact_info(self, phone, email, address, service_area, business_hours):
        """Update contact information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO contact_info (id, phone, email, address, service_area, business_hours)
            VALUES (1, ?, ?, ?, ?, ?)
        ''', (phone, email, address, service_area, business_hours))
        conn.commit()
        conn.close()
    
    def get_services(self):
        """Get all active services"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, description, base_price 
            FROM services 
            WHERE is_active = 1 
            ORDER BY name
        ''')
        services = cursor.fetchall()
        conn.close()
        return services
    
    def get_time_slots(self):
        """Get all active time slots"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, time_slot 
            FROM time_slots 
            WHERE is_active = 1 
            ORDER BY time_slot
        ''')
        time_slots = cursor.fetchall()
        conn.close()
        return time_slots
    
    def get_availability(self, date):
        """Get availability for a specific date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ts.id, ts.time_slot, a.is_available
            FROM time_slots ts
            LEFT JOIN availability a ON ts.id = a.time_slot_id AND a.date = ?
            WHERE ts.is_active = 1
            ORDER BY ts.time_slot
        ''', (date,))
        availability = cursor.fetchall()
        conn.close()
        return availability
    
    def set_availability(self, date, time_slot_id, is_available):
        """Set availability for a specific date and time slot"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO availability (date, time_slot_id, is_available)
            VALUES (?, ?, ?)
        ''', (date, time_slot_id, is_available))
        conn.commit()
        conn.close()
    
    def add_service(self, name, description, base_price):
        """Add a new service"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO services (name, description, base_price)
            VALUES (?, ?, ?)
        ''', (name, description, base_price))
        service_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return service_id
    
    def update_service(self, service_id, name, description, base_price):
        """Update an existing service"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE services 
            SET name = ?, description = ?, base_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, description, base_price, service_id))
        conn.commit()
        conn.close()
    
    def delete_service(self, service_id):
        """Delete a service (soft delete by setting is_active to 0)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE services 
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (service_id,))
        conn.commit()
        conn.close()
    
    def add_booking(self, service_id, customer_name, customer_phone, customer_email, 
                  customer_address, service_date, time_slot, description, total_price):
        """Add a new booking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bookings 
            (service_id, customer_name, customer_phone, customer_email, 
             customer_address, service_date, time_slot, description, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (service_id, customer_name, customer_phone, customer_email,
               customer_address, service_date, time_slot, description, total_price))
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return booking_id
    
    def get_gallery_photos(self, category=None):
        """Get all gallery photos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if category:
            cursor.execute('SELECT * FROM gallery_photos WHERE category = ? AND is_active = 1 ORDER BY display_order ASC', (category,))
        else:
            cursor.execute('SELECT * FROM gallery_photos WHERE is_active = 1 ORDER BY display_order ASC')
        
        photos = cursor.fetchall()
        conn.close()
        return photos
    
    def add_gallery_photo(self, filename, title, description, category='general', display_order=0):
        """Add a new gallery photo"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gallery_photos (filename, title, description, category, display_order)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, title, description, category, display_order))
        photo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return photo_id
    
    def update_gallery_photo(self, photo_id, title, description, category, display_order):
        """Update gallery photo information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE gallery_photos 
            SET title = ?, description = ?, category = ?, display_order = ?
            WHERE id = ?
        ''', (title, description, category, display_order, photo_id))
        conn.commit()
        conn.close()
    
    def delete_gallery_photo(self, photo_id):
        """Delete a gallery photo"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE gallery_photos SET is_active = 0 WHERE id = ?', (photo_id,))
        conn.commit()
        conn.close()
    
    def update_photo_order(self, photo_orders):
        """Update display order of multiple photos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for photo_id, order in photo_orders:
            cursor.execute('UPDATE gallery_photos SET display_order = ? WHERE id = ?', (order, photo_id))
        conn.commit()
        conn.close()
    
    def get_bookings(self, date=None):
        """Get bookings, optionally filtered by date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if date:
            cursor.execute('''
                SELECT b.*, s.name as service_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                WHERE b.service_date = ?
                ORDER BY b.service_date, b.time_slot
            ''', (date,))
        else:
            cursor.execute('''
                SELECT b.*, s.name as service_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                ORDER BY b.service_date DESC, b.time_slot
            ''')
        
        bookings = cursor.fetchall()
        conn.close()
        return bookings
