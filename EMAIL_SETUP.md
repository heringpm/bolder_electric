# Email Setup for Bolder Electric Contact Form

The contact form now sends submissions to `info@bolderelectric.com` using a local postfix SMTP server - no external email account required!

## Option 1: Local Postfix (Recommended - Simplest)

### Install and Configure Postfix

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postfix mailutils
```

**During installation:**
- Choose "Internet Site" 
- System mail name: `bolderelectric.com` (or your domain)

**Configure postfix to send from your domain:**
```bash
sudo nano /etc/postfix/main.cf
```

Add/update these lines:
```
myhostname = bolderelectric.com
mydomain = bolderelectric.com
myorigin = $mydomain
mydestination = $myhostname, localhost.$mydomain, localhost
relayhost = 
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128
```

**Restart postfix:**
```bash
sudo systemctl restart postfix
```

### Test Postfix
```bash
echo "Test email" | mail -s "Test" info@bolderelectric.com
```

## Option 2: Gmail SMTP (If you prefer external service)

See the original setup instructions if you want to use Gmail instead.

## AWS Elastic Beanstalk Setup

If using AWS, you may need to configure postfix:

```bash
# Install postfix on EC2 instances
sudo yum install postfix  # Amazon Linux
# or
sudo apt install postfix  # Ubuntu

# Configure and start
sudo systemctl enable postfix
sudo systemctl start postfix
```

## Email Content

The email will include:
- Customer name, email, phone
- Service type requested  
- Message details
- Professional formatting

## Troubleshooting

**Email not sending?**
1. Check postfix is running: `sudo systemctl status postfix`
2. Check mail queue: `mailq`
3. Check logs: `sudo tail -f /var/log/mail.log`

**Spam issues?**
1. Set up proper DNS records (SPF, DKIM)
2. Configure reverse DNS for your server IP
3. Consider using a dedicated email service for better deliverability

## Security Notes

- Local postfix doesn't require external credentials
- Ensure your server IP has proper reverse DNS
- Monitor for abuse to prevent being blacklisted
