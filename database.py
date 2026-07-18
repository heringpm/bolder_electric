import os
import sqlite3
from datetime import datetime, timedelta
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
except Exception:
    psycopg2 = None


class DatabaseManager:
    def __init__(self, db_path='bolder_electric.db'):
        self.db_path = db_path
        self.database_url = os.environ.get('DATABASE_URL', '').strip()
        self.use_postgres = self.database_url.startswith('postgres://') or self.database_url.startswith('postgresql://')

        if self.use_postgres and psycopg2 is None:
            raise RuntimeError('DATABASE_URL points to PostgreSQL but psycopg2 is not installed. Add psycopg2-binary to requirements.')

        self.init_database()

    def _prepare_query(self, query):
        if self.use_postgres:
            return query.replace('?', '%s')
        return query

    def get_connection(self):
        if self.use_postgres:
            return psycopg2.connect(self.database_url)
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _fetchone_value(self, cursor):
        row = cursor.fetchone()
        return row[0] if row else None

    def _parse_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace(' ', 'T'))
        except Exception:
            return None

    def init_database(self):
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if self.use_postgres:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_users (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'admin',
                        two_factor_secret TEXT,
                        two_factor_enabled BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        failed_attempts INTEGER DEFAULT 0,
                        locked_until TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS access_logs (
                        id SERIAL PRIMARY KEY,
                        username TEXT,
                        ip_address TEXT,
                        user_agent TEXT,
                        action TEXT,
                        success BOOLEAN,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contact_info (
                        id INTEGER PRIMARY KEY,
                        phone TEXT NOT NULL,
                        email TEXT NOT NULL,
                        address TEXT NOT NULL,
                        service_area TEXT NOT NULL,
                        business_hours TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contact_submissions (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        service_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        acknowledged BOOLEAN DEFAULT FALSE,
                        acknowledged_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS site_settings (
                        id SERIAL PRIMARY KEY,
                        setting_key TEXT UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS services (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        base_price REAL NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS time_slots (
                        id SERIAL PRIMARY KEY,
                        time_slot TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS availability (
                        id SERIAL PRIMARY KEY,
                        date DATE NOT NULL,
                        time_slot_id INTEGER REFERENCES time_slots (id),
                        is_available BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(date, time_slot_id)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bookings (
                        id SERIAL PRIMARY KEY,
                        service_id INTEGER REFERENCES services (id),
                        customer_name TEXT NOT NULL,
                        customer_phone TEXT NOT NULL,
                        customer_email TEXT NOT NULL,
                        customer_address TEXT NOT NULL,
                        service_date DATE NOT NULL,
                        time_slot TEXT NOT NULL,
                        description TEXT,
                        total_price REAL NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gallery_photos (
                        id SERIAL PRIMARY KEY,
                        filename TEXT NOT NULL,
                        title TEXT,
                        description TEXT,
                        category TEXT DEFAULT 'general',
                        display_order INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reviews (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        source TEXT NOT NULL DEFAULT 'website',
                        review_text TEXT NOT NULL,
                        is_featured BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS blog_posts (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        slug TEXT NOT NULL UNIQUE,
                        excerpt TEXT,
                        content TEXT,
                        hero_image TEXT,
                        pdf_url TEXT,
                        template INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'draft',
                        published_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'admin',
                        two_factor_secret TEXT,
                        two_factor_enabled BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        failed_attempts INTEGER DEFAULT 0,
                        locked_until TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1
                    )
                ''')

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

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contact_info (
                        id INTEGER PRIMARY KEY,
                        phone TEXT NOT NULL,
                        email TEXT NOT NULL,
                        address TEXT NOT NULL,
                        service_area TEXT NOT NULL,
                        business_hours TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS contact_submissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        service_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT,
                        acknowledged BOOLEAN DEFAULT 0,
                        acknowledged_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS site_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        setting_key TEXT UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

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

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS time_slots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        time_slot TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

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
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_availability_date_slot ON availability(date, time_slot_id)')

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

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        source TEXT NOT NULL DEFAULT 'website',
                        review_text TEXT NOT NULL,
                        is_featured BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS blog_posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        slug TEXT NOT NULL UNIQUE,
                        excerpt TEXT,
                        content TEXT,
                        hero_image TEXT,
                        pdf_url TEXT,
                        template INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'draft',
                        published_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            self._ensure_admin_user_security_columns(cursor)
            self._ensure_contact_submission_columns(cursor)
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print(f'Database initialization error: {e}')
            raise
        finally:
            if conn:
                conn.close()

        self.seed_default_data()

    def _ensure_admin_user_security_columns(self, cursor):
        """Ensure admin_users columns exist for older installations."""
        if self.use_postgres:
            cursor.execute('ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT \'admin\'')
            cursor.execute('ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS two_factor_secret TEXT')
            cursor.execute('ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN DEFAULT FALSE')
        else:
            cursor.execute('PRAGMA table_info(admin_users)')
            columns = [row[1] for row in cursor.fetchall()]
            if 'role' not in columns:
                cursor.execute('ALTER TABLE admin_users ADD COLUMN role TEXT NOT NULL DEFAULT \'admin\'')
            if 'two_factor_secret' not in columns:
                try:
                    cursor.execute('ALTER TABLE admin_users ADD COLUMN two_factor_secret TEXT')
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise
            if 'two_factor_enabled' not in columns:
                try:
                    cursor.execute('ALTER TABLE admin_users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT 0')
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise

    def _ensure_contact_submission_columns(self, cursor):
        """Ensure contact_submissions supports acknowledge workflow."""
        if self.use_postgres:
            cursor.execute('ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN DEFAULT FALSE')
            cursor.execute('ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP')
        else:
            cursor.execute('PRAGMA table_info(contact_submissions)')
            columns = [row[1] for row in cursor.fetchall()]
            if 'acknowledged' not in columns:
                try:
                    cursor.execute('ALTER TABLE contact_submissions ADD COLUMN acknowledged BOOLEAN DEFAULT 0')
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise
            if 'acknowledged_at' not in columns:
                try:
                    cursor.execute('ALTER TABLE contact_submissions ADD COLUMN acknowledged_at TIMESTAMP')
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise

    def seed_default_data(self):
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self._prepare_query('SELECT COUNT(*) FROM admin_users'))
            if self._fetchone_value(cursor) == 0:
                bootstrap_user = (os.environ.get('ADMIN_BOOTSTRAP_USERNAME') or 'admin').strip() or 'admin'
                bootstrap_password = (os.environ.get('ADMIN_BOOTSTRAP_PASSWORD') or '').strip()
                generated_password = False
                if not bootstrap_password:
                    bootstrap_password = secrets.token_urlsafe(18)
                    generated_password = True

                self.create_admin_user(bootstrap_user, bootstrap_password)
                print(f'Created bootstrap admin user: {bootstrap_user}')
                if generated_password:
                    print('WARNING: ADMIN_BOOTSTRAP_PASSWORD was not set. Generated one-time admin password:')
                    print(bootstrap_password)
                else:
                    print('Bootstrap admin password loaded from ADMIN_BOOTSTRAP_PASSWORD.')

            cursor.execute(self._prepare_query('SELECT COUNT(*) FROM contact_info'))
            if self._fetchone_value(cursor) == 0:
                cursor.execute(self._prepare_query('''
                    INSERT INTO contact_info (id, phone, email, address, service_area, business_hours)
                    VALUES (1, ?, ?, ?, ?, ?)
                '''), (
                    '(951) 397-4025',
                    'info@bolderelectric.com',
                    '30019 Buck Tail Drive, Menifee, CA 92587',
                    'Riverside County & Surrounding Areas',
                    'Mon-Fri: 8AM-6PM, Emergency: 24/7'
                ))
                print('Created contact info')

            # Seed notification routing settings.
            default_contact_notify = 'support@bolderelectric.com'
            default_booking_notify = os.environ.get('BOOKING_NOTIFICATION_EMAIL', 'info@bolderelectric.com')
            settings_to_seed = [
                ('contact_notification_email', default_contact_notify),
                ('booking_notification_email', default_booking_notify)
            ]
            for setting_key, setting_value in settings_to_seed:
                cursor.execute(self._prepare_query('SELECT COUNT(*) FROM site_settings WHERE setting_key = ?'), (setting_key,))
                if self._fetchone_value(cursor) == 0:
                    if self.use_postgres:
                        cursor.execute(self._prepare_query('''
                            INSERT INTO site_settings (setting_key, setting_value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT (setting_key) DO NOTHING
                        '''), (setting_key, setting_value))
                    else:
                        cursor.execute(self._prepare_query('''
                            INSERT OR IGNORE INTO site_settings (setting_key, setting_value, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                        '''), (setting_key, setting_value))

            cursor.execute(self._prepare_query('SELECT COUNT(*) FROM services'))
            if self._fetchone_value(cursor) == 0:
                default_services = [
                    ('Commercial Electrical', 'Complete electrical solutions for businesses, offices, and commercial properties', 150.0),
                    ('Residential Electrical', 'Professional electrical services for homes, apartments, and residential complexes', 100.0),
                    ('Emergency Service', '24/7 emergency electrical repair services', 250.0),
                    ('Panel Upgrade', 'Electrical panel upgrades and replacements', 300.0),
                    ('Lighting Installation', 'Indoor and outdoor lighting installation services', 125.0)
                ]
                cursor.executemany(self._prepare_query('''
                    INSERT INTO services (name, description, base_price)
                    VALUES (?, ?, ?)
                '''), default_services)
                print('Created default services')

            cursor.execute(self._prepare_query('SELECT COUNT(*) FROM time_slots'))
            if self._fetchone_value(cursor) == 0:
                default_time_slots = [
                    ('8:00 AM',), ('9:00 AM',), ('10:00 AM',), ('11:00 AM',),
                    ('12:00 PM',), ('1:00 PM',), ('2:00 PM',), ('3:00 PM',), ('4:00 PM',)
                ]
                cursor.executemany(self._prepare_query('INSERT INTO time_slots (time_slot) VALUES (?)'), default_time_slots)
                print('Created time slots')

            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print(f'Seeding error: {e}')
        finally:
            if conn:
                conn.close()

    def hash_password(self, password, salt=None):
        # Legacy compatibility: when salt is provided, compute historical SHA256 hash.
        if salt is not None:
            password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return password_hash, salt

        # Default for new/updated passwords: Werkzeug PBKDF2/Scrypt hash.
        password_hash = generate_password_hash(password)
        return password_hash, ''

    def verify_password(self, password, stored_hash, salt):
        """Verify both modern Werkzeug hashes and legacy SHA256+salt hashes.
        Returns (is_valid, needs_upgrade_to_modern_hash).
        """
        if not stored_hash:
            return False, False

        if stored_hash.startswith(('pbkdf2:', 'scrypt:')):
            try:
                return check_password_hash(stored_hash, password), False
            except Exception:
                return False, False

        if not salt:
            return False, False

        legacy_hash, _ = self.hash_password(password, salt)
        is_valid = legacy_hash == stored_hash
        return is_valid, is_valid

    def create_admin_user(self, username, password, role='admin'):
        password_hash, salt = self.hash_password(password)
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if self.use_postgres:
                cursor.execute(self._prepare_query('''
                    INSERT INTO admin_users (username, password_hash, salt, role)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (username) DO NOTHING
                '''), (username, password_hash, salt, role))
            else:
                cursor.execute(self._prepare_query('''
                    INSERT OR IGNORE INTO admin_users (username, password_hash, salt, role)
                    VALUES (?, ?, ?, ?)
                '''), (username, password_hash, salt, role))
            conn.commit()
        finally:
            conn.close()

    def verify_admin_login(self, username, password, ip_address, user_agent):
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self._prepare_query('''
                SELECT id, password_hash, salt, failed_attempts, locked_until, is_active, role
                FROM admin_users
                WHERE username = ?
            '''), (username,))

            user = cursor.fetchone()
            if not user:
                self.log_access(username, ip_address, user_agent, 'login_attempt', False)
                return False, 'Invalid credentials', None

            user_id, stored_hash, salt, failed_attempts, locked_until, is_active, role = user
            locked_until_dt = self._parse_datetime(locked_until)

            if locked_until_dt and locked_until_dt > datetime.now():
                self.log_access(username, ip_address, user_agent, 'login_attempt_locked', False)
                return False, 'Account locked due to too many failed attempts', None

            if not is_active:
                self.log_access(username, ip_address, user_agent, 'login_attempt_inactive', False)
                return False, 'Account is disabled', None

            password_ok, needs_upgrade = self.verify_password(password, stored_hash, salt)
            if password_ok:
                if needs_upgrade:
                    new_hash, new_salt = self.hash_password(password)
                    cursor.execute(self._prepare_query('''
                        UPDATE admin_users
                        SET password_hash = ?, salt = ?
                        WHERE id = ?
                    '''), (new_hash, new_salt, user_id))
                cursor.execute(self._prepare_query('''
                    UPDATE admin_users
                    SET failed_attempts = 0, last_login = CURRENT_TIMESTAMP, locked_until = NULL
                    WHERE id = ?
                '''), (user_id,))
                self.log_access(username, ip_address, user_agent, 'login_success', True)
                conn.commit()
                return True, 'Login successful', role or 'admin'

            failed_attempts += 1
            cursor.execute(self._prepare_query('''
                UPDATE admin_users
                SET failed_attempts = ?
                WHERE id = ?
            '''), (failed_attempts, user_id))

            if failed_attempts >= 5:
                lock_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                cursor.execute(self._prepare_query('''
                    UPDATE admin_users
                    SET locked_until = ?
                    WHERE id = ?
                '''), (lock_until, user_id))

            self.log_access(username, ip_address, user_agent, 'login_failed', False)
            conn.commit()
            return False, 'Invalid credentials', None

        except Exception as e:
            if conn:
                conn.rollback()
            return False, f'Database error: {str(e)}', None
        finally:
            if conn:
                conn.close()

    def verify_login_password(self, username, password, ip_address, user_agent):
        """Verify username/password and return 2FA metadata for step-up auth."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self._prepare_query('''
                SELECT id, password_hash, salt, failed_attempts, locked_until, is_active, role, two_factor_enabled, two_factor_secret
                FROM admin_users
                WHERE username = ?
            '''), (username,))

            user = cursor.fetchone()
            if not user:
                self.log_access(username, ip_address, user_agent, 'login_attempt', False)
                return False, 'Invalid credentials', None

            user_id, stored_hash, salt, failed_attempts, locked_until, is_active, role, two_factor_enabled, two_factor_secret = user
            locked_until_dt = self._parse_datetime(locked_until)

            if locked_until_dt and locked_until_dt > datetime.now():
                self.log_access(username, ip_address, user_agent, 'login_attempt_locked', False)
                return False, 'Account locked due to too many failed attempts', None

            if not is_active:
                self.log_access(username, ip_address, user_agent, 'login_attempt_inactive', False)
                return False, 'Account is disabled', None

            password_ok, needs_upgrade = self.verify_password(password, stored_hash, salt)
            if password_ok:
                if needs_upgrade:
                    new_hash, new_salt = self.hash_password(password)
                    cursor.execute(self._prepare_query('''
                        UPDATE admin_users
                        SET password_hash = ?, salt = ?
                        WHERE id = ?
                    '''), (new_hash, new_salt, user_id))
                cursor.execute(self._prepare_query('''
                    UPDATE admin_users
                    SET failed_attempts = 0, locked_until = NULL
                    WHERE id = ?
                '''), (user_id,))
                self.log_access(username, ip_address, user_agent, 'login_password_ok', True)
                conn.commit()
                return True, 'Password verified', {
                    'id': user_id,
                    'username': username,
                    'role': role or 'admin',
                    'two_factor_enabled': bool(two_factor_enabled),
                    'two_factor_secret': two_factor_secret
                }

            failed_attempts += 1
            cursor.execute(self._prepare_query('''
                UPDATE admin_users
                SET failed_attempts = ?
                WHERE id = ?
            '''), (failed_attempts, user_id))

            if failed_attempts >= 5:
                lock_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                cursor.execute(self._prepare_query('''
                    UPDATE admin_users
                    SET locked_until = ?
                    WHERE id = ?
                '''), (lock_until, user_id))

            self.log_access(username, ip_address, user_agent, 'login_failed', False)
            conn.commit()
            return False, 'Invalid credentials', None
        except Exception as e:
            if conn:
                conn.rollback()
            return False, f'Database error: {str(e)}', None
        finally:
            if conn:
                conn.close()

    def record_login_success(self, user_id, username, ip_address, user_agent):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET failed_attempts = 0, last_login = CURRENT_TIMESTAMP, locked_until = NULL
            WHERE id = ?
        '''), (user_id,))
        self.log_access(username, ip_address, user_agent, 'login_success', True)
        conn.commit()
        conn.close()

    def log_access(self, username, ip_address, user_agent, action, success):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self._prepare_query('''
                INSERT INTO access_logs (username, ip_address, user_agent, action, success)
                VALUES (?, ?, ?, ?, ?)
            '''), (username, ip_address, user_agent, action, success))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_access_logs(self, limit=100):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT username, ip_address, action, success, timestamp
            FROM access_logs
            ORDER BY timestamp DESC
            LIMIT ?
        '''), (limit,))
        logs = cursor.fetchall()
        conn.close()
        return logs

    def update_admin_password(self, username, new_password):
        password_hash, salt = self.hash_password(new_password)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL
            WHERE username = ?
        '''), (password_hash, salt, username))
        conn.commit()
        conn.close()

    def get_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT id, username, role, is_active, created_at, last_login, two_factor_enabled
            FROM admin_users
            ORDER BY username
        '''))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_user_by_username(self, username):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT id, username, role, is_active
            FROM admin_users
            WHERE username = ?
            LIMIT 1
        '''), (username,))
        row = cursor.fetchone()
        conn.close()
        return row

    def create_user(self, username, password, role):
        self.create_admin_user(username, password, role)

    def update_user_role(self, user_id, role):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET role = ?
            WHERE id = ?
        '''), (role, user_id))
        conn.commit()
        conn.close()

    def update_user_password(self, user_id, new_password):
        password_hash, salt = self.hash_password(new_password)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL
            WHERE id = ?
        '''), (password_hash, salt, user_id))
        conn.commit()
        conn.close()

    def set_user_active(self, user_id, is_active):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET is_active = ?
            WHERE id = ?
        '''), (bool(is_active), user_id))
        conn.commit()
        conn.close()

    def set_user_two_factor(self, user_id, secret, enabled=True):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET two_factor_secret = ?, two_factor_enabled = ?
            WHERE id = ?
        '''), (secret, bool(enabled), user_id))
        conn.commit()
        conn.close()

    def clear_user_two_factor(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        disabled_value = 'FALSE' if self.use_postgres else '0'
        cursor.execute(self._prepare_query('''
            UPDATE admin_users
            SET two_factor_secret = NULL, two_factor_enabled = ''' + disabled_value + '''
            WHERE id = ?
        '''), (user_id,))
        conn.commit()
        conn.close()

    def get_user_two_factor(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT two_factor_enabled, two_factor_secret
            FROM admin_users
            WHERE id = ?
            LIMIT 1
        '''), (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False, None
        return bool(row[0]), row[1]

    def get_contact_info(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('SELECT phone, email, address, service_area, business_hours FROM contact_info LIMIT 1'))
        contact = cursor.fetchone()
        conn.close()
        return contact

    def get_site_setting(self, key, default=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT setting_value
            FROM site_settings
            WHERE setting_key = ?
            LIMIT 1
        '''), (key,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return row[0]
        return default

    def set_site_setting(self, key, value):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO site_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            '''), (key, value))
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO site_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            '''), (key, value))
        conn.commit()
        conn.close()

    def update_contact_info(self, phone, email, address, service_area, business_hours):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO contact_info (id, phone, email, address, service_area, business_hours, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    address = EXCLUDED.address,
                    service_area = EXCLUDED.service_area,
                    business_hours = EXCLUDED.business_hours,
                    updated_at = CURRENT_TIMESTAMP
            '''), (phone, email, address, service_area, business_hours))
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO contact_info (id, phone, email, address, service_area, business_hours, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    phone = excluded.phone,
                    email = excluded.email,
                    address = excluded.address,
                    service_area = excluded.service_area,
                    business_hours = excluded.business_hours,
                    updated_at = CURRENT_TIMESTAMP
            '''), (phone, email, address, service_area, business_hours))
        conn.commit()
        conn.close()

    def add_contact_submission(self, name, email, phone, service_type, message, ip_address=None, user_agent=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO contact_submissions (name, email, phone, service_type, message, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            '''), (name, email, phone, service_type, message, ip_address, user_agent))
            submission_id = cursor.fetchone()[0]
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO contact_submissions (name, email, phone, service_type, message, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''), (name, email, phone, service_type, message, ip_address, user_agent))
            submission_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return submission_id

    def get_contact_submissions(self, limit=200):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT id, name, email, phone, service_type, message, ip_address, user_agent, acknowledged, acknowledged_at, created_at
            FROM contact_submissions
            ORDER BY created_at DESC
            LIMIT ?
        '''), (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def acknowledge_contact_submission(self, submission_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE contact_submissions
            SET acknowledged = ?, acknowledged_at = CURRENT_TIMESTAMP
            WHERE id = ?
        '''), (True if self.use_postgres else 1, submission_id))
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def delete_contact_submission(self, submission_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('DELETE FROM contact_submissions WHERE id = ?'), (submission_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_services(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        active_filter = 'TRUE' if self.use_postgres else '1'
        cursor.execute(self._prepare_query('''
            SELECT id, name, description, base_price
            FROM services
            WHERE is_active = ''' + active_filter + '''
            ORDER BY name
        '''))
        services = cursor.fetchall()
        conn.close()
        return services

    def add_review(self, name, rating, source, review_text, is_featured=True):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO reviews (name, rating, source, review_text, is_featured)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
            '''), (name, int(rating), source, review_text, bool(is_featured)))
            review_id = cursor.fetchone()[0]
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO reviews (name, rating, source, review_text, is_featured)
                VALUES (?, ?, ?, ?, ?)
            '''), (name, int(rating), source, review_text, 1 if is_featured else 0))
            review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return review_id

    def get_top_reviews(self, limit=5):
        conn = self.get_connection()
        cursor = conn.cursor()
        featured = 'TRUE' if self.use_postgres else '1'
        cursor.execute(self._prepare_query(f'''
            SELECT id, name, rating, source, review_text, created_at
            FROM reviews
            WHERE is_featured = {featured}
            ORDER BY created_at DESC
            LIMIT ?
        '''), (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_service_by_id(self, service_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('SELECT id, name, description, base_price FROM services WHERE id = ?'), (service_id,))
        service = cursor.fetchone()
        conn.close()
        return service

    def get_time_slots(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        active_filter = 'TRUE' if self.use_postgres else '1'
        cursor.execute(self._prepare_query('''
            SELECT id, time_slot
            FROM time_slots
            WHERE is_active = ''' + active_filter + '''
            ORDER BY time_slot
        '''))
        time_slots = cursor.fetchall()
        conn.close()
        return time_slots

    def get_availability(self, date):
        conn = self.get_connection()
        cursor = conn.cursor()
        active_filter = 'TRUE' if self.use_postgres else '1'
        cursor.execute(self._prepare_query('''
            SELECT ts.id, ts.time_slot, a.is_available
            FROM time_slots ts
            LEFT JOIN availability a ON ts.id = a.time_slot_id AND a.date = ?
            WHERE ts.is_active = ''' + active_filter + '''
            ORDER BY ts.time_slot
        '''), (date,))
        availability = cursor.fetchall()
        conn.close()
        return availability

    def set_availability(self, date, time_slot_id, is_available):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            INSERT INTO availability (date, time_slot_id, is_available)
            VALUES (?, ?, ?)
            ON CONFLICT (date, time_slot_id) DO UPDATE SET
                is_available = EXCLUDED.is_available
        '''), (date, time_slot_id, is_available))
        conn.commit()
        conn.close()

    def add_service(self, name, description, base_price):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO services (name, description, base_price)
                VALUES (?, ?, ?)
                RETURNING id
            '''), (name, description, base_price))
            service_id = cursor.fetchone()[0]
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO services (name, description, base_price)
                VALUES (?, ?, ?)
            '''), (name, description, base_price))
            service_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return service_id

    def update_service(self, service_id, name, description, base_price):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE services
            SET name = ?, description = ?, base_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        '''), (name, description, base_price, service_id))
        conn.commit()
        conn.close()

    def delete_service(self, service_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        inactive_value = 'FALSE' if self.use_postgres else '0'
        cursor.execute(self._prepare_query('''
            UPDATE services
            SET is_active = ''' + inactive_value + ''', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        '''), (service_id,))
        conn.commit()
        conn.close()

    def add_booking(self, service_id, customer_name, customer_phone, customer_email,
                    customer_address, service_date, time_slot, description, total_price):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO bookings
                (service_id, customer_name, customer_phone, customer_email,
                 customer_address, service_date, time_slot, description, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            '''), (service_id, customer_name, customer_phone, customer_email,
                   customer_address, service_date, time_slot, description, total_price))
            booking_id = cursor.fetchone()[0]
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO bookings
                (service_id, customer_name, customer_phone, customer_email,
                 customer_address, service_date, time_slot, description, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''), (service_id, customer_name, customer_phone, customer_email,
                   customer_address, service_date, time_slot, description, total_price))
            booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return booking_id

    def get_gallery_photos(self, category=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        active_filter = 'TRUE' if self.use_postgres else '1'
        if category:
            cursor.execute(self._prepare_query(
                'SELECT * FROM gallery_photos WHERE category = ? AND is_active = ' + active_filter + ' ORDER BY display_order ASC'
            ), (category,))
        else:
            cursor.execute(self._prepare_query(
                'SELECT * FROM gallery_photos WHERE is_active = ' + active_filter + ' ORDER BY display_order ASC'
            ))
        photos = cursor.fetchall()
        conn.close()
        return photos

    def add_gallery_photo(self, filename, title, description, category='general', display_order=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        if self.use_postgres:
            cursor.execute(self._prepare_query('''
                INSERT INTO gallery_photos (filename, title, description, category, display_order)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
            '''), (filename, title, description, category, display_order))
            photo_id = cursor.fetchone()[0]
        else:
            cursor.execute(self._prepare_query('''
                INSERT INTO gallery_photos (filename, title, description, category, display_order)
                VALUES (?, ?, ?, ?, ?)
            '''), (filename, title, description, category, display_order))
            photo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return photo_id

    def update_gallery_photo(self, photo_id, title, description, category, display_order=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if display_order is None:
            cursor.execute(self._prepare_query('''
                UPDATE gallery_photos
                SET title = ?, description = ?, category = ?
                WHERE id = ?
            '''), (title, description, category, photo_id))
        else:
            cursor.execute(self._prepare_query('''
                UPDATE gallery_photos
                SET title = ?, description = ?, category = ?, display_order = ?
                WHERE id = ?
            '''), (title, description, category, display_order, photo_id))
        conn.commit()
        conn.close()

    def delete_gallery_photo(self, photo_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        inactive_value = 'FALSE' if self.use_postgres else '0'
        cursor.execute(self._prepare_query('UPDATE gallery_photos SET is_active = ' + inactive_value + ' WHERE id = ?'), (photo_id,))
        conn.commit()
        conn.close()

    def update_photo_order(self, photo_orders):
        conn = self.get_connection()
        cursor = conn.cursor()
        for photo_id, order in photo_orders:
            cursor.execute(self._prepare_query(
                'UPDATE gallery_photos SET display_order = ? WHERE id = ?'
            ), (int(order), int(photo_id)))
        conn.commit()
        conn.close()

    def get_bookings(self, date=None):
        conn = self.get_connection()
        cursor = conn.cursor()

        if date:
            cursor.execute(self._prepare_query('''
                SELECT b.*, s.name as service_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                WHERE b.service_date = ?
                ORDER BY b.service_date, b.time_slot
            '''), (date,))
        else:
            cursor.execute(self._prepare_query('''
                SELECT b.*, s.name as service_name
                FROM bookings b
                JOIN services s ON b.service_id = s.id
                ORDER BY b.service_date DESC, b.time_slot
            '''))

        bookings = cursor.fetchall()
        conn.close()
        return bookings

    def get_booking_by_id(self, booking_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            SELECT b.*, s.name as service_name
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.id = ?
        '''), (booking_id,))
        booking = cursor.fetchone()
        conn.close()
        return booking

    def update_booking_status(self, booking_id, status):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE bookings
            SET status = ?
            WHERE id = ?
        '''), (status, booking_id))
        conn.commit()
        conn.close()

    def update_booking(self, booking_id, customer_name, customer_phone, customer_email,
                       customer_address, service_date, time_slot, description, total_price):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('''
            UPDATE bookings
            SET customer_name = ?, customer_phone = ?, customer_email = ?,
                customer_address = ?, service_date = ?, time_slot = ?,
                description = ?, total_price = ?
            WHERE id = ?
        '''), (
            customer_name, customer_phone, customer_email, customer_address,
            service_date, time_slot, description, total_price, booking_id
        ))
        conn.commit()
        conn.close()

    def delete_booking(self, booking_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('DELETE FROM bookings WHERE id = ?'), (booking_id,))
        conn.commit()
        conn.close()

    # ── Blog ──────────────────────────────────────────────────────────────────

    def _row_to_dict(self, cursor, row):
        """Convert a DB row to a dict using cursor.description (works for both SQLite and Postgres)."""
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

    def get_blog_posts(self, status=None, limit=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        if status:
            q = 'SELECT * FROM blog_posts WHERE status = ? ORDER BY published_at DESC, created_at DESC'
            params = [status]
        else:
            q = 'SELECT * FROM blog_posts ORDER BY created_at DESC'
            params = []
        if limit:
            q += ' LIMIT ?'
            params.append(limit)
        cursor.execute(self._prepare_query(q), params)
        rows = cursor.fetchall()
        result = [self._row_to_dict(cursor, r) for r in rows]
        conn.close()
        return result

    def get_blog_post_by_slug(self, slug):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('SELECT * FROM blog_posts WHERE slug = ? AND status = ?'), (slug, 'published'))
        row = cursor.fetchone()
        result = self._row_to_dict(cursor, row)
        conn.close()
        return result

    def get_blog_post_by_id(self, post_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('SELECT * FROM blog_posts WHERE id = ?'), (post_id,))
        row = cursor.fetchone()
        result = self._row_to_dict(cursor, row)
        conn.close()
        return result

    def create_blog_post(self, title, slug, excerpt, content, hero_image, template, status, pdf_url=None):
        import datetime
        conn = self.get_connection()
        cursor = conn.cursor()
        published_at = datetime.datetime.utcnow().isoformat() if status == 'published' else None
        cursor.execute(self._prepare_query('''
            INSERT INTO blog_posts (title, slug, excerpt, content, hero_image, pdf_url, template, status, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''), (title, slug, excerpt, content, hero_image, pdf_url, template, status, published_at))
        post_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return post_id

    def update_blog_post(self, post_id, title, slug, excerpt, content, hero_image, template, status, pdf_url=None):
        import datetime
        conn = self.get_connection()
        cursor = conn.cursor()
        existing = self.get_blog_post_by_id(post_id)
        published_at = existing.get('published_at') if existing else None
        if status == 'published' and not published_at:
            published_at = datetime.datetime.utcnow().isoformat()
        # Keep existing pdf_url if not explicitly passed
        if pdf_url is None and existing:
            pdf_url = existing.get('pdf_url')
        cursor.execute(self._prepare_query('''
            UPDATE blog_posts
            SET title=?, slug=?, excerpt=?, content=?, hero_image=?, pdf_url=?, template=?, status=?, published_at=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        '''), (title, slug, excerpt, content, hero_image, pdf_url, template, status, published_at, post_id))
        conn.commit()
        conn.close()

    def delete_blog_post(self, post_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(self._prepare_query('DELETE FROM blog_posts WHERE id = ?'), (post_id,))
        conn.commit()
        conn.close()
