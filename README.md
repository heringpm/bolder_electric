# Bolder Electric - Python Web Application

A professional web application for Bolder Electric, built with Flask and designed for deployment on AWS EC2.

## Features

- Modern, responsive design
- Commercial and residential service sections
- Contact form with database storage
- Admin panel for managing services and bookings
- Online booking system with availability management
- Access logging and security features
- Mobile-friendly navigation
- Professional color scheme (red, black, and gold)
- SEO-friendly structure

## Local Development

### Prerequisites
- Python 3.8+
- pip

### Installation

1. Clone or download this project
2. Navigate to the project directory:
   ```bash
   cd bolder_electric
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Run the application:
   ```bash
   python app.py
   ```

6. Open your browser and navigate to `http://localhost:8080`

7. **Access Admin Panel**
   - Navigate to `http://localhost:8080/admin`
   - Login with username: `admin`, password: `usLaG4wLCnJW1F`
   - The database will be created automatically on first run

## AWS EC2 Deployment

### Prerequisites
- AWS account
- EC2 instance (Amazon Linux 2023 recommended)
- Domain name (optional)

### Production Port Plan (No Overlap)
- `Nginx`: `80` (and `443` after SSL)
- `Gunicorn`: `127.0.0.1:8000` (local only)
- `PostgreSQL`: `127.0.0.1:5432` (or RDS endpoint)
- `Flask dev server` (`python app.py`): use only for local testing, not production

Do not run `python app.py` and Gunicorn at the same time in production.

### Step-by-Step Deployment (Known-Good)

1. **Connect to EC2**
   ```bash
   ssh -i your-key.pem ec2-user@your-ec2-ip
   ```

2. **Install OS packages**
   ```bash
   sudo dnf -y update
   sudo dnf -y install python3 python3-pip python3-virtualenv nginx postgresql15 postgresql15-server policycoreutils-python-utils
   sudo /usr/bin/postgresql-setup --initdb
   sudo systemctl enable --now nginx postgresql
   ```
   If your AMI exposes a different PostgreSQL version, list available packages first:
   ```bash
   sudo dnf search postgresql | head -n 40
   ```

3. **Clone app**
   ```bash
   sudo mkdir -p /var/www
   sudo chown -R ec2-user:ec2-user /var/www
   git clone https://github.com/heringpm/bolder_electric.git /var/www/bolder_electric
   cd /var/www/bolder_electric
   ```

4. **Create Python env + install deps**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **Create PostgreSQL DB + user**
   ```bash
   sudo -u postgres psql -c "CREATE USER bolder_app WITH PASSWORD 'change_this_password';"
   sudo -u postgres psql -c "CREATE DATABASE bolder_electric OWNER bolder_app;"
   sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE bolder_electric TO bolder_app;"
   ```

6. **Create environment file for systemd**
   ```bash
   sudo tee /etc/bolder_electric.env >/dev/null <<'EOF'
   DATABASE_URL=postgresql://bolder_app:change_this_password@127.0.0.1:5432/bolder_electric
   FLASK_ENV=production
   MAX_UPLOAD_MB=25
   # SMTP provider settings (required for contact/booking emails)
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USERNAME=apikey
   SMTP_PASSWORD=your_smtp_password_or_api_key
   SMTP_USE_TLS=true
   SMTP_USE_SSL=false
   SMTP_FROM_EMAIL=noreply@bolderelectric.com
   SMTP_FROM_NAME=Bolder Electric Website
   BOOKING_NOTIFICATION_EMAIL=info@bolderelectric.com
   EOF
   ```

7. **Create systemd service (Gunicorn on 127.0.0.1:8000)**
   ```bash
   sudo tee /etc/systemd/system/bolder_electric.service >/dev/null <<'EOF'
   [Unit]
   Description=Bolder Electric Gunicorn
   After=network.target

   [Service]
   User=ec2-user
   Group=nginx
   WorkingDirectory=/var/www/bolder_electric
   EnvironmentFile=/etc/bolder_electric.env
   ExecStart=/var/www/bolder_electric/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   EOF
   ```

8. **Start app service**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now bolder_electric
   sudo systemctl status bolder_electric --no-pager
   ```

9. **Configure Nginx reverse proxy**
   ```bash
   sudo tee /etc/nginx/conf.d/bolder_electric.conf >/dev/null <<'EOF'
   server {
       listen 80;
       server_name your-domain.com your-ec2-ip;
       client_max_body_size 25M;

       location /static/ {
           alias /var/www/bolder_electric/static/;
       }

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   EOF
   ```

   `MAX_UPLOAD_MB` and `client_max_body_size` should match.

10. **Allow Nginx proxy under SELinux**
    ```bash
    sudo setsebool -P httpd_can_network_connect 1
    sudo semanage fcontext -a -t httpd_sys_content_t "/var/www/bolder_electric/static(/.*)?"
    sudo restorecon -Rv /var/www/bolder_electric/static
    ```

11. **Reload Nginx**
    ```bash
    sudo nginx -t
    sudo systemctl restart nginx
    ```

12. **Open firewall/security group**
    ```bash
    # EC2 Security Group: allow inbound TCP 80 and 443 from 0.0.0.0/0
    # Amazon Linux host firewall (firewalld):
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
    ```

13. **Validate each layer**
   ```bash
    # Ports that should be listening
    sudo ss -ltnp | egrep ':80|:8000|:5432'

    # App through gunicorn (local)
    curl -I http://127.0.0.1:8000/

    # App through nginx (public path on instance)
   curl -I http://127.0.0.1/
   ```

14. **If gallery upload returns `413 Request Entity Too Large`**
   ```bash
   # 1) Confirm nginx limit
   sudo nginx -T | grep -n client_max_body_size

   # 2) Confirm app limit
   sudo grep -n MAX_UPLOAD_MB /etc/bolder_electric.env

   # 3) Reload both services after changes
   sudo systemctl restart bolder_electric
   sudo systemctl restart nginx
   ```
15. **If emails are not sending**
   ```bash
   # 1) Verify SMTP env vars loaded
   sudo systemctl show bolder_electric --property=Environment | tr ' ' '\n' | egrep 'SMTP_|BOOKING_NOTIFICATION_EMAIL'

   # 2) Restart app after env updates
   sudo systemctl restart bolder_electric

   # 3) Check app logs for SMTP errors
   sudo journalctl -u bolder_electric -n 120 --no-pager
   ```
16. **Optional SSL**
    ```bash
    sudo dnf -y install certbot python3-certbot-nginx
    sudo certbot --nginx -d your-domain.com
    ```

## Database Information

### Database Type
- **PostgreSQL (recommended for production)** via `DATABASE_URL`
- **SQLite fallback** for local quick-start when `DATABASE_URL` is not set

### Database Tables
- `admin_users` - Admin authentication
- `access_logs` - Login attempt tracking
- `contact_info` - Website contact details
- `contact_submissions` - Contact form leads (name/email/phone/project details)
- `services` - Electrical services offered
- `time_slots` - Available booking times
- `availability` - Service availability calendar
- `bookings` - Customer booking records
- `gallery_photos` - Gallery image metadata

### Default Admin Credentials
- **Username**: `admin`
- **Password**: `usLaG4wLCnJW1F`

### PostgreSQL Setup
Use these steps to install PostgreSQL and run this app on Postgres instead of SQLite.

1. Install PostgreSQL
   - macOS (Homebrew):
     ```bash
     brew install postgresql@16
     brew services start postgresql@16
     ```
   - Amazon Linux 2023:
     ```bash
     sudo dnf -y install postgresql15 postgresql15-server
     sudo /usr/bin/postgresql-setup --initdb
     sudo systemctl enable --now postgresql
     ```
     If `postgresql15*` is unavailable, use the version shown by:
     ```bash
     sudo dnf search postgresql | head -n 40
     ```

2. Create application database and user
   - Open the Postgres shell as the `postgres` superuser:
     ```bash
     sudo -u postgres psql
     ```
   - Run:
     ```sql
     CREATE USER bolder_app WITH PASSWORD 'change_this_password';
     CREATE DATABASE bolder_electric OWNER bolder_app;
     GRANT ALL PRIVILEGES ON DATABASE bolder_electric TO bolder_app;
     \q
     ```

3. Set `DATABASE_URL`
   ```bash
   export DATABASE_URL="postgresql://bolder_app:change_this_password@localhost:5432/bolder_electric"
   ```

4. (Optional) persist `DATABASE_URL` for future shells
   ```bash
   echo 'export DATABASE_URL="postgresql://bolder_app:change_this_password@localhost:5432/bolder_electric"' >> ~/.zshrc
   source ~/.zshrc
   ```

5. Verify database connection
   ```bash
   psql "$DATABASE_URL" -c "\conninfo"
   ```

6. Start the app (tables auto-create on first run)
   ```bash
   python app.py
   ```

### Migrate Existing SQLite Data to PostgreSQL
```bash
export DATABASE_URL=\"postgresql://USER:PASSWORD@HOST:5432/DB_NAME\"
python scripts/migrate_sqlite_to_postgres.py --sqlite bolder_electric.db
```

### PostgreSQL Backup / Restore
Backup:
```bash
pg_dump \"$DATABASE_URL\" > bolder_electric_backup_$(date +%Y%m%d).sql
```

Restore:
```bash
psql \"$DATABASE_URL\" < bolder_electric_backup_YYYYMMDD.sql
```

## Application Structure

```
bolder_electric/
├── app.py                 # Main Flask application
├── database.py            # Database management and initialization
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── bolder_electric.db     # SQLite database (created automatically)
├── templates/
│   ├── index.html        # Main homepage
│   ├── admin.html        # Admin panel
│   ├── login.html        # Admin login
│   ├── schedule.html     # Booking scheduling
│   └── account.html      # Account management
└── static/
    ├── css/
    │   └── style.css     # Styling
    ├── images/           # Logo and other images
    ├── robots.txt       # SEO robots file
    └── sitemap.xml      # SEO sitemap
```

## Customization

### Adding Your Logo
1. Place your logo file in `/static/images/`
2. Update the HTML template to reference your logo:
   ```html
   <img src="{{ url_for('static', filename='images/your-logo.png') }}" alt="Bolder Electric Logo">
   ```

### Updating Contact Information
Edit the contact details in `templates/index.html`:
- Phone number
- Email address
- Business hours

### Modifying Services
Update the services section in `templates/index.html` to match your specific offerings.

## Security Considerations

- In production, Gunicorn should run on `127.0.0.1:8000` only
- Admin panel is protected with secure login
- Access logging tracks all login attempts
- Database uses password hashing for admin users
- Nginx handles external traffic on port 80/443
- Gunicorn runs as a systemd service
- Static files are served directly by Nginx for better performance

## Troubleshooting

### Common Issues

1. **Application won't start**
   - Check if all dependencies are installed
   - Verify the virtual environment is activated
   - Check system logs: `sudo journalctl -u bolder_electric`
   - Ensure database permissions are correct

2. **Port overlap / address already in use**
   - Check active listeners:
     ```bash
     sudo ss -ltnp | egrep ':80|:8000|:8080|:5432'
     ```
   - Stop Flask dev server if running:
     ```bash
     pkill -f "python app.py" || true
     ```
   - Restart production services:
     ```bash
     sudo systemctl restart bolder_electric nginx
     ```

3. **Database errors**
   - Check write permissions: `ls -la bolder_electric.db`
   - Ensure proper ownership: `sudo chown ec2-user:nginx bolder_electric.db`
   - Check for database lock: `lsof bolder_electric.db`

4. **Admin login issues**
   - Verify admin user exists in database
   - Check access logs for failed attempts
   - Reset admin password if needed

5. **Nginx errors**
   - Test Nginx configuration: `sudo nginx -t`
   - Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`

6. **Permission issues**
   - Ensure proper ownership: `sudo chown -R ec2-user:nginx /var/www/bolder_electric`
   - Check file permissions

## Performance Optimization

- Gunicorn runs with 3 worker processes (adjust based on your EC2 instance size)
- Static files are served directly by Nginx
- Consider enabling caching headers for static assets
- Monitor resource usage and adjust worker count accordingly

## Support

For issues related to:
- AWS EC2: Contact AWS Support
- Application code: Check the Flask documentation
- Server configuration: Refer to Amazon Linux 2023 and Nginx documentation
