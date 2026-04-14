# Email Setup (SMTP Provider)

The app now sends all contact/booking emails through a configurable SMTP provider.
This is production-safe and works on EC2 without relying on local postfix.

## Required Environment Variables

Set these in `/etc/bolder_electric.env`:

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your_smtp_password_or_api_key
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_FROM_EMAIL=noreply@bolderelectric.com
SMTP_FROM_NAME=Bolder Electric Website
BOOKING_NOTIFICATION_EMAIL=info@bolderelectric.com
```

## Common Providers

### SendGrid SMTP

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<SENDGRID_API_KEY>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

### Google Workspace / Gmail SMTP

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@yourdomain.com
SMTP_PASSWORD=<APP_PASSWORD>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

## Apply Changes

```bash
sudo systemctl restart bolder_electric
```

## Verify on Server

```bash
# Ensure env vars are present
sudo systemctl show bolder_electric --property=Environment | tr ' ' '\n' | egrep 'SMTP_|BOOKING_NOTIFICATION_EMAIL'

# Watch app logs for mail errors
sudo journalctl -u bolder_electric -f
```

## Notes

- If `SMTP_HOST` is not set, the app falls back to local `localhost` SMTP.
- Contact form notifications go to the contact email stored in admin settings.
- New booking request notifications go to `BOOKING_NOTIFICATION_EMAIL` (defaults to `info@bolderelectric.com`).
