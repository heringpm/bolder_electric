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
import random
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
canonical_host = (os.environ.get('CANONICAL_HOST') or 'bolderelectric.com').strip().lower()
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

CITY_LANDING_PAGES = {
    'murrieta-ca': {
        'city': 'Murrieta',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'murrieta-ca',
        'title': 'Electrician in Murrieta, CA | Electrical Panel Repair, Replacement & Upgrades',
        'description': 'Bolder Electric provides electrical panel repair, electrical panel replacement, electrical panel upgrades, commercial electrical services, and emergency electrician response in Murrieta, CA.',
        'keywords': 'electrician murrieta ca, electrical panel repair murrieta ca, electrical panel repair murrieta, electrical panel replacement murrieta, electrical panel upgrade murrieta ca, murrieta electrical panel upgrades, emergency electrician murrieta',
        'hero_title': 'Electrical Panel Repair, Replacement & Electrician Services in Murrieta, CA',
        'hero_text': 'Bolder Electric serves Murrieta with electrical panel repair, electrical panel replacement planning, panel upgrades, residential troubleshooting, commercial electrical service, and emergency electrical response delivered with reliable, code-compliant workmanship.',
        'service_points': [
            'Electrical panel repair in Murrieta, including breaker troubleshooting and overheating or damage diagnostics',
            'Electrical panel replacement and electrical panel upgrade planning for homes and facilities in Murrieta',
            'Commercial electrical services for offices, retail, and industrial facilities',
            'Residential electrical repairs, rewiring, and home electrical upgrades',
            'Emergency electrician service with rapid diagnostics and response'
        ],
        'faq': [
            ('Do you provide commercial electrical services in Murrieta?', 'Yes. We support Murrieta businesses with service upgrades, distribution improvements, lighting, troubleshooting, and ongoing electrical maintenance.'),
            ('Can I request emergency electrician service in Murrieta, CA?', 'Yes. We provide emergency electrician response in Murrieta for outages, hazards, and urgent electrical issues.'),
            ('Do you handle electrical panel repair in Murrieta, CA?', 'Yes. We diagnose electrical panel issues in Murrieta and recommend repair or replacement based on safety, condition, and load requirements.'),
            ('Do you provide electrical panel upgrades in Murrieta, CA?', 'Yes. We complete electrical panel upgrades in Murrieta when homes or facilities need more capacity, safer equipment, or updated service components.'),
            ('Can you help with electrical panel replacement in Murrieta?', 'Yes. If a panel is outdated, damaged, or no longer safe to repair, we can plan and complete electrical panel replacement in Murrieta.'),
            ('Do you handle home electrical upgrades in Murrieta?', 'Yes. We complete home electrical upgrades, panel improvements, dedicated circuits, and residential safety corrections.')
        ],
        'related_services': [
            {'slug': 'electrical-panel-upgrades', 'label': 'Electrical Panel Upgrades'},
            {'slug': 'emergency-electrician-services', 'label': 'Emergency Electrician Services'},
            {'slug': 'residential-electrician-services', 'label': 'Residential Electrician Services'},
            {'slug': 'commercial-electrical-services', 'label': 'Commercial Electrical Services'}
        ]
    },
    'temecula-ca': {
        'city': 'Temecula',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'temecula-ca',
        'title': 'Electrician in Temecula, CA | Residential, Commercial & Emergency Electrical Services',
        'description': 'Bolder Electric delivers residential electrician services, commercial electrical services, electrical panel upgrades, and emergency electrical response in Temecula, CA and nearby Southern California cities.',
        'keywords': 'electrician temecula ca, residential electrician temecula, residential electrician temecula ca, commercial electrical services temecula ca, emergency electrician temecula ca',
        'hero_title': 'Residential & Commercial Electrician Services in Temecula, CA',
        'hero_text': 'Bolder Electric serves Temecula with residential electrician services, commercial electrical support, panel upgrades, and emergency response backed by safety, reliability, and clear communication.',
        'service_points': [
            'Residential electrician services for repairs, outlets, switches, lighting, and home electrical upgrades',
            'Commercial electrical build-outs, infrastructure improvements, and maintenance',
            'Electrical panel upgrades to improve safety and service capacity',
            'Emergency electrician support for critical electrical failures'
        ],
        'faq': [
            ('Do you serve both homes and businesses in Temecula?', 'Yes. We provide both residential and commercial electrical services throughout Temecula and nearby areas.'),
            ('Can you help if I need a residential electrician in Temecula?', 'Yes. We provide residential electrician services in Temecula for troubleshooting, repairs, lighting, dedicated circuits, and home electrical upgrades.'),
            ('Can you help with panel upgrades in Temecula?', 'Yes. We perform electrical panel upgrades and panel repair to modernize systems and improve long-term reliability.'),
            ('Is scheduling online an instant booking?', 'No. Scheduling is a request process, and our team confirms appointment details directly with you.')
        ]
    },
    'lake-elsinore-ca': {
        'city': 'Lake Elsinore',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'lake-elsinore-ca',
        'title': 'Electrician in Lake Elsinore, CA | Panel Upgrades, Commercial & Residential Service',
        'description': 'Bolder Electric provides dependable electrician services in Lake Elsinore, CA including commercial electrical services, residential electrician work, emergency electrical response, and panel upgrades.',
        'keywords': 'electrician lake elsinore, electrician lake elsinore ca, lake elsinore electrician, electricians in lake elsinore ca, electrical panel upgrades lake elsinore ca',
        'hero_title': 'Reliable Electrician in Lake Elsinore, CA',
        'hero_text': 'We provide electrician services in Lake Elsinore for commercial facilities and homes, including diagnostics, electrical panel upgrades, code corrections, and emergency repairs.',
        'service_points': [
            'Commercial electrical services for expanding businesses and facilities',
            'Residential electrician support for homes, remodels, repairs, and dedicated circuit work',
            'Electrical panel upgrades in Lake Elsinore and safety-focused electrical corrections',
            'Emergency electrical service for urgent power and safety issues'
        ],
        'faq': [
            ('Do you offer emergency electrician service in Lake Elsinore?', 'Yes. We provide emergency electrical response in Lake Elsinore for urgent electrical issues and hazardous failures.'),
            ('Can I hire an electrician in Lake Elsinore for home or business work?', 'Yes. We provide electrician services in Lake Elsinore for both commercial facilities and residential properties.'),
            ('Can you complete electrical panel upgrades for older homes?', 'Yes. We upgrade older electrical panels and perform associated code corrections where needed.'),
            ('Do you handle commercial electrical projects in Lake Elsinore?', 'Yes. We support commercial projects including tenant improvements, service upgrades, and lighting systems.')
        ]
    },
    'menifee-ca': {
        'city': 'Menifee',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'menifee-ca',
        'title': 'Electrician in Menifee, CA | Emergency, Commercial, Residential & Panel Upgrades',
        'description': 'Bolder Electric is a licensed electrician in Menifee, CA providing commercial electrical services, residential electrician work, emergency electrical services, electrical panel upgrades, and electrical panel repair.',
        'keywords': 'electrician menifee ca, emergency electrician menifee ca, commercial electrical services menifee ca, residential electrician menifee ca, electrical panel upgrades menifee ca, electrical panel repair menifee ca, electrical repair menifee ca',
        'hero_title': 'Licensed Electrician Services in Menifee, CA',
        'hero_text': 'As a Menifee electrical contractor, Bolder Electric provides electrician services in Menifee, CA including commercial electrical services, residential electrician support, emergency electrical services, electrical panel repair, and electrical panel upgrades with dependable local response.',
        'service_points': [
            'Commercial electrical services for offices, schools, warehouses, and utility-related work',
            'Residential electrician services for upgrades, troubleshooting, and home electrical repairs',
            'Emergency electrical services in Menifee for outages, hazards, and urgent failures',
            'Electrical panel upgrades, electrical panel replacement, and electrical panel repair',
            'Electrical repairs for service calls, troubleshooting, lighting issues, and service changes'
        ],
        'faq': [
            ('Do you provide commercial electrical services in Menifee?', 'Yes. We provide commercial electrical services in Menifee including upgrades, distribution work, and diagnostics.'),
            ('Can you help if I need an electrician in Menifee, CA?', 'Yes. We provide electrician services in Menifee, CA for homes, businesses, panel work, troubleshooting, and emergency response.'),
            ('Can you help with residential electrical issues in Menifee, CA?', 'Yes. We provide residential electrician services in Menifee for repairs, upgrades, and safety-focused electrical improvements.'),
            ('Do you offer emergency electrical services in Menifee?', 'Yes. We provide emergency electrician response in Menifee for urgent outages, unsafe electrical conditions, and critical troubleshooting needs.'),
            ('Do you perform electrical panel upgrades in Menifee, CA?', 'Yes. We handle electrical panel upgrades and panel repair in Menifee, including service changes and safety-focused modernization work.'),
            ('Do you serve areas outside Menifee?', 'Yes. We serve Menifee, surrounding Riverside County cities, and broader Southern California service areas.')
        ],
        'related_services': [
            {'slug': 'commercial-electrical-services', 'label': 'Commercial Electrical Services'},
            {'slug': 'emergency-electrician-services', 'label': 'Emergency Electrician Services'},
            {'slug': 'residential-electrician-services', 'label': 'Residential Electrician Services'},
            {'slug': 'electrical-panel-upgrades', 'label': 'Electrical Panel Upgrades'}
        ]
    },
    'perris-ca': {
        'city': 'Perris',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'perris-ca',
        'title': 'Electrician in Perris, CA | Commercial, Residential & Emergency Electrical Services',
        'description': 'Bolder Electric provides commercial electrical services, residential electrician support, emergency electrical response, and electrical panel upgrades in Perris, CA and surrounding Riverside County communities.',
        'hero_title': 'Dependable Electrician Services in Perris, CA',
        'hero_text': 'From business power upgrades to home electrical repairs, Bolder Electric delivers code-compliant electrical services across Perris and nearby Riverside County cities.',
        'service_points': [
            'Commercial electrical build-outs, upgrades, and maintenance',
            'Residential electrician services for troubleshooting and repairs',
            'Electrical panel upgrades, replacements, and safety corrections',
            'Emergency electrician response for urgent outages and hazards'
        ],
        'faq': [
            ('Do you provide commercial electrical services in Perris?', 'Yes. We support Perris businesses with commercial electrical upgrades, power distribution work, and electrical maintenance.'),
            ('Can I request emergency electrician service in Perris, CA?', 'Yes. We provide emergency electrician response in Perris for urgent electrical failures and safety issues.'),
            ('Do you work on residential electrical panel upgrades?', 'Yes. We provide residential electrical panel upgrades and related code-compliance improvements.')
        ]
    },
    'wildomar-ca': {
        'city': 'Wildomar',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'wildomar-ca',
        'title': 'Electrician in Wildomar, CA | Commercial, Residential & Emergency Electrical Services',
        'description': 'Bolder Electric delivers commercial electrical services, home electrical upgrades, emergency electrician response, and panel work in Wildomar, CA and nearby Southern California areas.',
        'hero_title': 'Professional Electrical Services in Wildomar, CA',
        'hero_text': 'Bolder Electric provides safe, reliable electrical services for businesses and homeowners in Wildomar, with a focus on long-term performance and responsive service.',
        'service_points': [
            'Commercial electrical services for offices and facilities',
            'Residential electrician support for homes and remodel projects',
            'Electrical panel upgrades and service capacity improvements',
            'Emergency electrical diagnostics and repair service'
        ],
        'faq': [
            ('Do you serve both homes and businesses in Wildomar?', 'Yes. We provide both residential and commercial electrical services throughout Wildomar and surrounding areas.'),
            ('Can you help with electrical troubleshooting in Wildomar?', 'Yes. We provide professional diagnostics and troubleshooting for intermittent or urgent electrical issues.'),
            ('Is scheduling online an instant appointment?', 'No. Scheduling is a request. Our team confirms date/time details directly with you.')
        ]
    },
    'hemet-ca': {
        'city': 'Hemet',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'hemet-ca',
        'title': 'Electrician in Hemet, CA | Commercial, Residential & Emergency Electrical Services',
        'description': 'Bolder Electric provides residential and commercial electrical services, emergency electrician support, and panel upgrades in Hemet, CA and surrounding Riverside County communities.',
        'hero_title': 'Trusted Electrician Services in Hemet, CA',
        'hero_text': 'We deliver electrical repairs, upgrades, and emergency response services in Hemet with quality workmanship and clear communication from start to finish.',
        'service_points': [
            'Commercial electrical services for active job sites and facilities',
            'Residential electrical repairs and home electrical upgrades',
            'Electrical panel repair, replacement, and upgrades',
            'Emergency electrician response when power or safety issues occur'
        ],
        'faq': [
            ('Can you handle both commercial and residential work in Hemet?', 'Yes. We provide full-scope electrical services for both homes and businesses in Hemet.'),
            ('Do you provide electrical panel upgrades in Hemet?', 'Yes. We perform panel upgrades and service improvements to support safety and capacity needs.'),
            ('Do you provide emergency electrical support?', 'Yes. We provide emergency response for urgent electrical issues in Hemet and nearby communities.')
        ]
    },
    'corona-ca': {
        'city': 'Corona',
        'county': 'Riverside County',
        'state': 'CA',
        'slug': 'corona-ca',
        'title': 'Electrician in Corona, CA | Commercial, Residential & Emergency Electrical Services',
        'description': 'Bolder Electric offers commercial electrical services, residential electrician support, emergency repairs, and electrical panel upgrades in Corona, CA and throughout Riverside County.',
        'hero_title': 'Commercial & Residential Electrician in Corona, CA',
        'hero_text': 'Bolder Electric serves Corona with professional electrical services for facilities and homes, including urgent repairs, upgrades, and long-term system improvements.',
        'service_points': [
            'Commercial electrical upgrades, tenant improvements, and maintenance',
            'Residential electrician support for service calls and upgrades',
            'Electrical panel upgrades, replacements, and corrections',
            'Emergency electrician service for urgent outages and failures'
        ],
        'faq': [
            ('Do you provide commercial electrical services in Corona?', 'Yes. We provide commercial electrical services in Corona for offices, facilities, and tenant improvement projects.'),
            ('Can you help with residential electrical upgrades in Corona, CA?', 'Yes. We provide residential electrician support including rewiring, panel upgrades, and dedicated circuits.'),
            ('Do you respond to emergency electrical issues?', 'Yes. We provide emergency electrical diagnostics and repair support in Corona and nearby cities.')
        ]
    }
}

SERVICE_LANDING_PAGES = {
    'commercial-electrical-services': {
        'slug': 'commercial-electrical-services',
        'title': 'Commercial Electrical Services | Bolder Electric',
        'description': 'Commercial electrical services for offices, industrial spaces, school districts, and utility-related projects across Riverside County and Southern California.',
        'h1': 'Commercial Electrical Services',
        'intro': 'Bolder Electric delivers dependable commercial electrical services for new construction, tenant improvements, infrastructure upgrades, and ongoing maintenance.',
        'bullets': [
            'New construction and tenant improvement electrical systems',
            'Service upgrades, power distribution, and infrastructure improvements',
            'Interior/exterior commercial lighting design and installation',
            'Switchgear, panel upgrades, and equipment replacement',
            'Preventive maintenance and system evaluations',
            'Emergency diagnostics and rapid electrical repairs'
        ],
        'faq': [
            ('What types of facilities do you serve?', 'We support offices, industrial spaces, schools, and utility-related facilities across Riverside County and Southern California.'),
            ('Can you support phased commercial projects?', 'Yes. We coordinate with project schedules and phases to keep work safe, compliant, and on timeline.')
        ]
    },
    'emergency-electrician-services': {
        'slug': 'emergency-electrician-services',
        'title': 'Emergency Electrician Services | Bolder Electric',
        'description': 'Emergency electrician services for urgent outages, hazards, and critical electrical failures across Riverside County and Southern California.',
        'h1': 'Emergency Electrician Services',
        'intro': 'When electrical issues cannot wait, Bolder Electric provides rapid-response emergency electrician services to diagnose hazards and stabilize systems safely.',
        'bullets': [
            'Urgent troubleshooting for outages and intermittent failures',
            'Electrical hazard assessment and immediate risk mitigation',
            'Emergency panel and circuit diagnostics',
            'Power restoration planning and corrective repairs',
            'Commercial and residential emergency response'
        ],
        'faq': [
            ('Do you provide emergency service after normal business hours?', 'Yes. We provide emergency response coverage and prioritize urgent electrical safety issues.'),
            ('Can emergency service include commercial sites?', 'Yes. We support both commercial facilities and residential properties during emergency calls.')
        ]
    },
    'residential-electrician-services': {
        'slug': 'residential-electrician-services',
        'title': 'Residential Electrician Services | Bolder Electric',
        'description': 'Residential electrician services including troubleshooting, rewiring, lighting, panel upgrades, and code corrections for homes across Riverside County.',
        'h1': 'Residential Electrician Services',
        'intro': 'Bolder Electric provides safe, clean, and code-compliant residential electrician services with clear communication and reliable workmanship.',
        'bullets': [
            'Home rewiring and electrical system upgrades',
            'Outlet, switch, and dedicated circuit installation',
            'Interior and exterior lighting installations',
            'Troubleshooting and electrical repair service calls',
            'Code corrections and electrical safety improvements'
        ],
        'faq': [
            ('Do you handle older home electrical upgrades?', 'Yes. We evaluate existing systems and recommend practical upgrades for safety and reliability.'),
            ('Can you install new dedicated circuits?', 'Yes. We install dedicated circuits for appliances, EV chargers, and specialty equipment.')
        ]
    },
    'electrical-panel-upgrades': {
        'slug': 'electrical-panel-upgrades',
        'title': 'Electrical Panel Upgrades | Bolder Electric',
        'description': 'Electrical panel upgrades, replacements, and panel repair services to improve safety, capacity, and reliability in homes and facilities.',
        'h1': 'Electrical Panel Upgrades',
        'intro': 'Bolder Electric performs electrical panel upgrades and related service improvements to support modern load demands and improve long-term system safety.',
        'bullets': [
            'Panel replacements and service capacity upgrades',
            'Electrical panel repair and troubleshooting',
            'Main breaker and distribution improvements',
            'Code-compliant modernization recommendations',
            'Residential and commercial panel solutions'
        ],
        'faq': [
            ('How do I know if I need a panel upgrade?', 'Frequent breaker trips, outdated equipment, or expanded electrical usage are common indicators.'),
            ('Do you provide both repair and replacement?', 'Yes. We assess your current equipment and recommend repair or replacement based on safety and performance.')
        ]
    },
    'ev-charger-installation': {
        'slug': 'ev-charger-installation',
        'title': 'EV Charger Installation | Bolder Electric',
        'description': 'Professional EV charger installation services for homes and facilities across Riverside County and Southern California.',
        'h1': 'EV Charger Installation',
        'intro': 'We install EV charging systems with proper circuit sizing, panel capacity evaluation, and code-compliant workmanship for reliable long-term charging.',
        'bullets': [
            'Residential EV charger installations',
            'Commercial and fleet charging infrastructure',
            'Circuit sizing and load calculation support',
            'Panel capacity review and upgrade recommendations',
            'Code-compliant installation and testing'
        ],
        'faq': [
            ('Can you install EV chargers at both homes and businesses?', 'Yes. We provide EV charger installation for residential and commercial properties.'),
            ('Do I need a panel upgrade for EV charging?', 'Some installations do. We evaluate your panel and recommend upgrades when needed.')
        ]
    },
    'lighting-installation-services': {
        'slug': 'lighting-installation-services',
        'title': 'Lighting Installation Services | Bolder Electric',
        'description': 'Indoor and outdoor lighting installation services for commercial and residential properties across Riverside County.',
        'h1': 'Lighting Installation Services',
        'intro': 'Bolder Electric provides lighting installation and upgrade services that improve safety, visibility, and energy efficiency for both commercial and residential properties.',
        'bullets': [
            'Interior and exterior lighting installation',
            'LED retrofit and fixture upgrades',
            'Site and security lighting improvements',
            'Control and dimming system integration',
            'Lighting troubleshooting and repair service'
        ],
        'faq': [
            ('Do you install both indoor and outdoor lighting?', 'Yes. We install and upgrade interior, exterior, site, and security lighting systems.'),
            ('Can you help reduce energy use with lighting upgrades?', 'Yes. We provide LED-focused upgrade options designed to improve efficiency and performance.')
        ]
    }
}


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
    canonical_hosts = {canonical_host}
    if canonical_host.startswith('www.'):
        canonical_hosts.add(canonical_host[4:])
    else:
        canonical_hosts.add(f'www.{canonical_host}')

    if force_https and not _is_secure_request() and host not in localhost_hosts:
        https_url = request.url.replace('http://', 'https://', 1)
        return redirect(https_url, code=301)

    if host not in localhost_hosts and host not in canonical_hosts:
        target = canonical_host
        scheme = 'https' if (_is_secure_request() or force_https) else request.scheme
        path = request.full_path if request.query_string else request.path
        if path.endswith('?'):
            path = path[:-1]
        return redirect(f'{scheme}://{target}{path}', code=301)

    if host == f'www.{canonical_host}':
        scheme = 'https' if (_is_secure_request() or force_https) else request.scheme
        path = request.full_path if request.query_string else request.path
        if path.endswith('?'):
            path = path[:-1]
        return redirect(f'{scheme}://{canonical_host}{path}', code=301)

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
    context = _build_home_context()
    return render_template('index.html', **context)


def _build_home_context():
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
    
    captcha_left = random.randint(2, 9)
    captcha_right = random.randint(1, 8)
    session['contact_captcha_answer'] = str(captcha_left + captcha_right)
    session['contact_captcha_issued_at'] = int(time.time())

    return {
        'contact': contact_data,
        'service_descriptions': service_descriptions,
        'service_prices': service_prices,
        'contact_captcha_question': f'{captcha_left} + {captcha_right}'
    }


@app.route('/home2')
def home2():
    context = _build_home_context()
    return render_template('home2.html', **context)

@app.route('/gallery')
def gallery():
    photos = db.get_gallery_photos()
    return render_template('gallery.html', photos=photos)

@app.route('/commercial')
def commercial():
    return redirect(url_for('service_landing', slug='commercial-electrical-services'), code=301)

@app.route('/residential')
def residential():
    return redirect(url_for('service_landing', slug='residential-electrician-services'), code=301)

@app.route('/about')
def about():
    return redirect(url_for('home') + '#about')


def _render_city_landing(slug):
    city_data = CITY_LANDING_PAGES.get(slug)
    if not city_data:
        return redirect(url_for('home'))
    return render_template('city_landing.html', city=city_data)

def _render_service_landing(slug):
    service_data = SERVICE_LANDING_PAGES.get(slug)
    if not service_data:
        return redirect(url_for('home'))
    return render_template('service_landing.html', service=service_data)


@app.route('/electrician/murrieta-ca')
def city_murrieta():
    return _render_city_landing('murrieta-ca')


@app.route('/electrician/temecula-ca')
def city_temecula():
    return _render_city_landing('temecula-ca')


@app.route('/electrician/lake-elsinore-ca')
def city_lake_elsinore():
    return _render_city_landing('lake-elsinore-ca')


@app.route('/electrician/menifee-ca')
def city_menifee():
    return _render_city_landing('menifee-ca')

@app.route('/electrician/perris-ca')
def city_perris():
    return _render_city_landing('perris-ca')

@app.route('/electrician/wildomar-ca')
def city_wildomar():
    return _render_city_landing('wildomar-ca')

@app.route('/electrician/hemet-ca')
def city_hemet():
    return _render_city_landing('hemet-ca')

@app.route('/electrician/corona-ca')
def city_corona():
    return _render_city_landing('corona-ca')

@app.route('/services/<slug>')
def service_landing(slug):
    return _render_service_landing(slug)

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
        captcha_answer = (request.form.get('captcha_answer') or '').strip()
        website_field = (request.form.get('website') or '').strip()
        
        # Validate required fields
        if not all([name, email, phone, service_type, message]):
            return jsonify({
                'success': False,
                'message': 'Please fill out all required fields.'
            }), 400

        # Honeypot field should remain empty for humans.
        if website_field:
            return jsonify({
                'success': False,
                'message': 'Submission blocked. Please try again.'
            }), 400

        expected_captcha = (session.get('contact_captcha_answer') or '').strip()
        issued_at = int(session.get('contact_captcha_issued_at') or 0)
        captcha_ttl_seconds = 15 * 60
        if not expected_captcha or not captcha_answer or captcha_answer != expected_captcha:
            return jsonify({
                'success': False,
                'message': 'Captcha verification failed. Please refresh and try again.'
            }), 400
        if issued_at and int(time.time()) - issued_at > captcha_ttl_seconds:
            return jsonify({
                'success': False,
                'message': 'Captcha expired. Please refresh and try again.'
            }), 400

        # One-time captcha token usage.
        session.pop('contact_captcha_answer', None)
        session.pop('contact_captcha_issued_at', None)

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
        review_text = (data.get('review_text') or '').strip()
        rating_raw = data.get('rating')

        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            rating = 0

        source = 'google'

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
    entries.extend([(f"/electrician/{slug}", 'weekly', '0.8') for slug in CITY_LANDING_PAGES.keys()])
    entries.extend([(f"/services/{slug}", 'weekly', '0.8') for slug in SERVICE_LANDING_PAGES.keys()])
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
    return send_from_directory('static/images', 'favicon.png')


@app.route('/hello-world')
@app.route('/hello-world/')
def legacy_hello_world_redirect():
    return redirect(url_for('home'), code=301)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug_mode = _env_bool('FLASK_DEBUG', False)
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
