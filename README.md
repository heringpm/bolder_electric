# Bolder Electric - Python Web Application

A professional web application for Bolder Electric, built with Flask and designed for deployment on AWS EC2.

## Features

- Modern, responsive design
- Commercial and residential service sections
- Contact form
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

6. Open your browser and navigate to `http://localhost:5000`

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

5. **Test the Application**
   ```bash
   python app.py
   ```
   Verify it runs on port 5000, then stop with Ctrl+C

6. **Install and Configure Gunicorn**
   ```bash
   pip install gunicorn
   ```

7. **Create Gunicorn Service File**
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

8. **Start and Enable Gunicorn Service**
   ```bash
   sudo systemctl start bolder_electric
   sudo systemctl enable bolder_electric
   sudo systemctl status bolder_electric
   ```

9. **Configure Nginx**
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

10. **Enable the Site**
    ```bash
    sudo ln -s /etc/nginx/sites-available/bolder_electric /etc/nginx/sites-enabled
    sudo nginx -t
    sudo systemctl restart nginx
    ```

11. **Configure Firewall**
    ```bash
    sudo ufw allow 'Nginx Full'
    sudo ufw allow ssh
    sudo ufw enable
    ```

12. **Optional: Set up SSL with Let's Encrypt**
    ```bash
    sudo apt install certbot python3-certbot-nginx -y
    sudo certbot --nginx -d your-domain.com
    ```

## Application Structure

```
bolder_electric/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/
│   └── index.html        # Main HTML template
└── static/
    ├── css/
    │   └── style.css     # Styling
    └── images/           # Logo and other images
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

- The application runs on port 5000 internally
- Nginx handles external traffic on port 80/443
- Gunicorn runs as a systemd service
- Static files are served directly by Nginx for better performance

## Troubleshooting

### Common Issues

1. **Application won't start**
   - Check if all dependencies are installed
   - Verify the virtual environment is activated
   - Check system logs: `sudo journalctl -u bolder_electric`

2. **Nginx errors**
   - Test Nginx configuration: `sudo nginx -t`
   - Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`

3. **Permission issues**
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
