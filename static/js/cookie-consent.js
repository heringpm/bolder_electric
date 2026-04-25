(function () {
    var CONSENT_KEY = 'bolder_cookie_consent_v2';
    var CONSENT_ACCEPTED = 'accepted';
    var CONSENT_REJECTED = 'rejected';
    var scriptTag = document.currentScript;
    var measurementId = (scriptTag && scriptTag.dataset && scriptTag.dataset.gaMeasurementId) || '';

    function readConsent() {
        try {
            return window.localStorage.getItem(CONSENT_KEY);
        } catch (_err) {
            return null;
        }
    }

    function saveConsent(value) {
        try {
            window.localStorage.setItem(CONSENT_KEY, value);
        } catch (_err) {
            // Ignore storage failures.
        }
    }

    function loadAnalytics() {
        if (!measurementId || window.__bolderGaLoaded) return;
        window.__bolderGaLoaded = true;

        window.dataLayer = window.dataLayer || [];
        window.gtag = window.gtag || function gtag() {
            window.dataLayer.push(arguments);
        };
        window.gtag('js', new Date());
        window.gtag('config', measurementId);

        var gaScript = document.createElement('script');
        gaScript.async = true;
        gaScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(measurementId);
        document.head.appendChild(gaScript);
    }

    function closeBanner() {
        var banner = document.getElementById('cookie-consent-banner');
        if (banner) banner.remove();
    }

    function buildBanner() {
        var existing = document.getElementById('cookie-consent-banner');
        if (existing) return;

        var banner = document.createElement('div');
        banner.id = 'cookie-consent-banner';
        banner.className = 'cookie-consent';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-live', 'polite');
        banner.innerHTML = ''
            + '<div class="cookie-consent__content">'
            + '  <p class="cookie-consent__text">We use cookies to understand website traffic and improve your experience. You can accept or decline analytics cookies.</p>'
            + '  <div class="cookie-consent__actions">'
            + '    <button type="button" class="cookie-consent__btn cookie-consent__btn--accept" id="cookie-consent-accept">Accept</button>'
            + '    <button type="button" class="cookie-consent__btn cookie-consent__btn--decline" id="cookie-consent-decline">Decline</button>'
            + '  </div>'
            + '</div>';

        document.body.appendChild(banner);

        var acceptBtn = document.getElementById('cookie-consent-accept');
        var declineBtn = document.getElementById('cookie-consent-decline');

        if (acceptBtn) {
            acceptBtn.addEventListener('click', function () {
                saveConsent(CONSENT_ACCEPTED);
                loadAnalytics();
                closeBanner();
            });
        }

        if (declineBtn) {
            declineBtn.addEventListener('click', function () {
                saveConsent(CONSENT_REJECTED);
                closeBanner();
            });
        }
    }

    function init() {
        var consent = readConsent();
        if (consent === CONSENT_ACCEPTED) {
            loadAnalytics();
            return;
        }
        if (consent === CONSENT_REJECTED) {
            return;
        }
        buildBanner();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
