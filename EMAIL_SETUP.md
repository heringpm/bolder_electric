# Email Setup for Bolder Electric Contact Form

The contact form now sends submissions to `info@bolderelectric.com`. To enable email sending, you need to configure SMTP settings.

## Setup Instructions

### 1. Configure Gmail SMTP (Recommended)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Bolder Electric"

### 2. Set Environment Variables

On your server, set these environment variables:

```bash
export EMAIL_USER="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
```

For AWS Elastic Beanstalk:
```bash
eb setenv EMAIL_USER="your-email@gmail.com" EMAIL_PASSWORD="your-app-password"
```

### 3. Alternative SMTP Services

You can also use other SMTP providers by modifying the `send_contact_email()` function in `app.py`:

- **SendGrid**: Update SMTP server to `smtp.sendgrid.net:587`
- **AWS SES**: Use boto3 instead of smtplib
- **Outlook**: Use `smtp-mail.outlook.com:587`

### 4. Test the Configuration

1. Deploy the updated code
2. Fill out the contact form on the website
3. Check if email arrives at `info@bolderelectric.com`

## Email Content

The email will include:
- Customer name, email, phone
- Service type requested
- Message details
- Professional formatting

## Troubleshooting

**Email not sending?**
1. Check environment variables are set
2. Verify Gmail app password is correct
3. Check server logs for error messages

**Spam issues?**
1. Set up SPF/DKIM records for your domain
2. Use a dedicated email service like SendGrid for better deliverability

## Security Notes

- Never commit email credentials to git
- Use environment variables for sensitive data
- Consider using a dedicated transactional email service for production
