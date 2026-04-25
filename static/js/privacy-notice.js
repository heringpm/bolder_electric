(function () {
    var CONSENT_KEY = 'bolder_cookie_consent_v3';
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
        var banner = document.getElementById('privacy-notice-banner');
        if (banner) banner.remove();
    }

    function attachHandlers() {
        var acceptBtn = document.getElementById('privacy-notice-accept');
        var declineBtn = document.getElementById('privacy-notice-decline');

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

    function buildBanner() {
        var existing = document.getElementById('privacy-notice-banner');
        if (existing) {
            attachHandlers();
            return;
        }

        var banner = document.createElement('div');
        banner.id = 'privacy-notice-banner';
        banner.className = 'privacy-notice';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-live', 'polite');
        banner.innerHTML = ''
            + '<div class="privacy-notice__content">'
            + '  <p class="privacy-notice__text">We use cookies to understand website traffic and improve your experience. You can accept or decline analytics cookies.</p>'
            + '  <div class="privacy-notice__actions">'
            + '    <button type="button" class="privacy-notice__btn privacy-notice__btn--accept" id="privacy-notice-accept">Accept</button>'
            + '    <button type="button" class="privacy-notice__btn privacy-notice__btn--decline" id="privacy-notice-decline">Decline</button>'
            + '  </div>'
            + '</div>';

        document.body.appendChild(banner);
        attachHandlers();
    }

    function init() {
        var consent = readConsent();
        if (consent === CONSENT_ACCEPTED) {
            loadAnalytics();
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
