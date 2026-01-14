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
- EC2 instance (Ubuntu 20.04+ recommended)
- Domain name (optional)

### Step-by-Step Deployment

1. **Connect to EC2 Instance**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   ```

2. **Update System and Install Dependencies**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3-pip python3-venv nginx -y
   ```

3. **Clone Your Application**
   ```bash
   git clone <your-repository-url> /var/www/bolder_electric
   cd /var/www/bolder_electric
   ```

4. **Set Up Python Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Set Up Database**
   ```bash
   # The application will automatically create the SQLite database
   # Ensure the application has write permissions to the project directory
   sudo chown -R ubuntu:www-data /var/www/bolder_electric
   sudo chmod -R 755 /var/www/bolder_electric
   ```

6. **Initialize Database and Admin User**
   ```bash
   # Run the application once to initialize the database
   python app.py &
   sleep 5
   kill %1
   
   # The database will be created automatically with:
   # - Default admin user: username 'admin', password 'usLaG4wLCnJW1F'
   # - Sample services and availability data
   ```

7. **Test the Application**
   ```bash
   python app.py
   ```
   Verify it runs on port 8080, then stop with Ctrl+C

8. **Install and Configure Gunicorn**
   ```bash
   pip install gunicorn
   ```

9. **Create Gunicorn Service File**
   ```bash
   sudo nano /etc/systemd/system/bolder_electric.service
   ```
   
   Add the following content:
   ```ini
   [Unit]
   Description=Bolder Electric Flask App
   After=network.target

   [Service]
   User=ubuntu
   Group=www-data
   WorkingDirectory=/var/www/bolder_electric
   ExecStart=/var/www/bolder_electric/venv/bin/gunicorn --workers 3 --bind unix:bolder_electric.sock -m 007 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

10. **Start and Enable Gunicorn Service**
   ```bash
   sudo systemctl start bolder_electric
   sudo systemctl enable bolder_electric
   sudo systemctl status bolder_electric
   ```

11. **Configure Nginx**
   ```bash
   sudo nano /etc/nginx/sites-available/bolder_electric
   ```
   
   Add the following configuration:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com your-ec2-ip;

       location / {
           include proxy_params;
           proxy_pass http://unix:/var/www/bolder_electric/bolder_electric.sock;
       }

       location /static {
           alias /var/www/bolder_electric/static;
       }
   }
   ```

12. **Enable the Site**
    ```bash
    sudo ln -s /etc/nginx/sites-available/bolder_electric /etc/nginx/sites-enabled
    sudo nginx -t
    sudo systemctl restart nginx
    ```

13. **Configure Firewall**
    ```bash
    sudo ufw allow 'Nginx Full'
    sudo ufw allow ssh
    sudo ufw enable
    ```

14. **Optional: Set up SSL with Let's Encrypt**
    ```bash
    sudo apt install certbot python3-certbot-nginx -y
    sudo certbot --nginx -d your-domain.com
    ```

## Database Information

### Database Type
- **SQLite** - File-based database, no separate server required
- **Database file**: `bolder_electric.db` (automatically created)

### Database Tables
- `admin_users` - Admin authentication
- `access_logs` - Login attempt tracking
- `contact_info` - Contact form submissions
- `services` - Electrical services offered
- `time_slots` - Available booking times
- `availability` - Service availability calendar
- `bookings` - Customer booking records

### Default Admin Credentials
- **Username**: `admin`
- **Password**: `usLaG4wLCnJW1F`

### Database Backup
To backup the database:
```bash
cp bolder_electric.db bolder_electric_backup_$(date +%Y%m%d).db
```

To restore:
```bash
cp bolder_electric_backup_YYYYMMDD.db bolder_electric.db
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

- The application runs on port 8080 internally
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

2. **Database errors**
   - Check write permissions: `ls -la bolder_electric.db`
   - Ensure proper ownership: `sudo chown ubuntu:www-data bolder_electric.db`
   - Check for database lock: `lsof bolder_electric.db`

3. **Admin login issues**
   - Verify admin user exists in database
   - Check access logs for failed attempts
   - Reset admin password if needed

4. **Nginx errors**
   - Test Nginx configuration: `sudo nginx -t`
   - Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`

5. **Permission issues**
   - Ensure proper ownership: `sudo chown -R ubuntu:www-data /var/www/bolder_electric`
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
- Server configuration: Refer to Ubuntu and Nginx documentation
