/**
 * Narration & Speech Timing Engine - Client Controller
 * Video Calculator Platform
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const textarea = document.getElementById('narrationText');
    const clearBtn = document.getElementById('clearTextBtn');
    const liveWordPill = document.getElementById('liveWordPill');
    const charCountDisplay = document.getElementById('charCountDisplay');
    const selectedWpmPill = document.getElementById('selectedWpmPill');
    const customDrawer = document.getElementById('customSpeedDrawer');
    const customWpmInput = document.getElementById('customWpmInput');
    const customSpeedError = document.getElementById('customSpeedError');
    const statusBadge = document.getElementById('calculationStatusBadge');
    const errorBanner = document.getElementById('errorBanner');

    // Metrics Display Elements
    const heroDurationDisplay = document.getElementById('heroDurationDisplay');
    const heroDurationReadable = document.getElementById('heroDurationReadable');
    const metricWordCount = document.getElementById('metricWordCount');
    const metricWpm = document.getElementById('metricWpm');
    const metricSeconds = document.getElementById('metricSeconds');
    const metricMinutes = document.getElementById('metricMinutes');
    const formulaExampleText = document.getElementById('formulaExampleText');

    // Configuration & State
    const CALCULATION_API_URL = '/calculators/talking-flyer/narration-test/calculate/';
    const DEBOUNCE_DELAY_MS = 280;
    const MIN_WPM = 60;
    const MAX_WPM = 240;

    let debounceTimer = null;
    let latestRequestId = 0;
    let currentWpm = 135; // Default Conversational speed

    /**
     * Reads the CSRF token from the DOM form token or cookie.
     */
    function getCsrfToken() {
        const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenInput && tokenInput.value) {
            return tokenInput.value;
        }
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return decodeURIComponent(value);
            }
        }
        return '';
    }

    /**
     * Quick client-side estimation of word count for instant typing feedback.
     * Matches the backend rule: whitespace-delimited tokens.
     */
    function countWordsLocally(text) {
        if (!text) return 0;
        const normalized = text.trim().replace(/\s+/g, ' ');
        if (!normalized) return 0;
        return normalized.split(' ').length;
    }

    /**
     * Updates client-side word count and character count badges immediately.
     */
    function updateLiveCounters() {
        const text = textarea.value || '';
        const words = countWordsLocally(text);
        liveWordPill.textContent = `${words} word${words === 1 ? '' : 's'}`;
        charCountDisplay.textContent = `${text.length} character${text.length === 1 ? '' : 's'}`;
    }

    /**
     * Updates the status badge UI.
     */
    function setStatus(status, text) {
        statusBadge.className = 'results-status-badge';
        if (status === 'loading') {
            statusBadge.classList.add('status-loading');
            statusBadge.textContent = text || 'Calculating...';
        } else if (status === 'error') {
            statusBadge.classList.add('status-error');
            statusBadge.textContent = text || 'Input Error';
        } else {
            statusBadge.classList.add('status-ready');
            statusBadge.textContent = text || 'Live';
        }
    }

    /**
     * Displays or hides the global error banner.
     */
    function showError(message) {
        if (message) {
            errorBanner.textContent = message;
            errorBanner.classList.add('visible');
            setStatus('error');
        } else {
            errorBanner.textContent = '';
            errorBanner.classList.remove('visible');
        }
    }

    /**
     * Determines current active WPM based on radio selection or custom input.
     */
    function resolveActiveWpm() {
        const selectedRadio = document.querySelector('input[name="speed_preset"]:checked');
        if (!selectedRadio) return currentWpm;

        if (selectedRadio.value === 'custom') {
            const customVal = parseInt(customWpmInput.value, 10);
            if (isNaN(customVal)) {
                customSpeedError.textContent = `Please enter a valid number between ${MIN_WPM} and ${MAX_WPM}.`;
                customSpeedError.style.display = 'block';
                return null;
            }
            if (customVal < MIN_WPM || customVal > MAX_WPM) {
                customSpeedError.textContent = `Speed must be between ${MIN_WPM} and ${MAX_WPM} WPM.`;
                customSpeedError.style.display = 'block';
                return null;
            }
            customSpeedError.style.display = 'none';
            return customVal;
        }

        customSpeedError.style.display = 'none';
        return parseInt(selectedRadio.value, 10);
    }

    /**
     * Renders backend calculation results to the UI.
     */
    function renderResults(data) {
        heroDurationDisplay.textContent = data.duration_display;
        heroDurationReadable.textContent = data.duration_readable;

        metricWordCount.textContent = data.word_count;
        metricWpm.textContent = data.wpm;
        metricSeconds.textContent = data.duration_seconds_formatted || data.duration_seconds.toFixed(2);
        metricMinutes.textContent = data.duration_minutes_formatted || data.duration_minutes.toFixed(2);

        selectedWpmPill.textContent = `${data.wpm} WPM`;
        liveWordPill.textContent = `${data.word_count} word${data.word_count === 1 ? '' : 's'}`;

        // Update example formula text
        if (data.word_count > 0) {
            formulaExampleText.textContent = `Current: ${data.word_count} words @ ${data.wpm} WPM = (${data.word_count} ÷ ${data.wpm}) × 60 = ${data.duration_seconds_formatted}s (${data.duration_readable}).`;
        } else {
            formulaExampleText.textContent = `Example: 150 words at 150 WPM = (150 ÷ 150) × 60 = 60.0 seconds (1 minute 0 seconds).`;
        }
    }

    /**
     * Sends calculation request to authoritative backend endpoint.
     */
    async function requestBackendCalculation() {
        const wpm = resolveActiveWpm();
        if (wpm === null) {
            setStatus('error', 'Invalid WPM');
            return;
        }

        currentWpm = wpm;
        showError(null);
        setStatus('loading');

        const requestId = ++latestRequestId;
        const text = textarea.value;

        try {
            const response = await fetch(CALCULATION_API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({
                    text: text,
                    wpm: currentWpm,
                }),
            });

            // Prevent older out-of-order responses from overwriting newer user changes
            if (requestId !== latestRequestId) {
                return;
            }

            const json = await response.json();

            if (!response.ok || !json.success) {
                showError(json.error || 'Validation error from calculation server.');
                setStatus('error');
                return;
            }

            renderResults(json.data);
            setStatus('ready');
        } catch (err) {
            if (requestId === latestRequestId) {
                showError('Network error while connecting to calculation engine. Please retry.');
                setStatus('error');
            }
        }
    }

    /**
     * Debounced wrapper to avoid flooding backend on every keystroke.
     */
    function triggerCalculationDebounced() {
        updateLiveCounters();
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(() => {
            requestBackendCalculation();
        }, DEBOUNCE_DELAY_MS);
    }

    // Event Listeners
    textarea.addEventListener('input', triggerCalculationDebounced);

    clearBtn.addEventListener('click', () => {
        textarea.value = '';
        textarea.focus();
        updateLiveCounters();
        requestBackendCalculation();
    });

    // Speed Preset Radio Changes
    const presetLabels = document.querySelectorAll('.speed-option-label');
    const radioInputs = document.querySelectorAll('input[name="speed_preset"]');

    radioInputs.forEach((radio) => {
        radio.addEventListener('change', () => {
            presetLabels.forEach((label) => label.classList.remove('active'));
            const parentLabel = radio.closest('.speed-option-label');
            if (parentLabel) parentLabel.classList.add('active');

            if (radio.value === 'custom') {
                customDrawer.classList.remove('hidden');
                customWpmInput.focus();
                if (!customWpmInput.value) {
                    customWpmInput.value = currentWpm || 140;
                }
            } else {
                customDrawer.classList.add('hidden');
                customSpeedError.style.display = 'none';
            }

            requestBackendCalculation();
        });
    });

    // Custom WPM Input Change
    customWpmInput.addEventListener('input', () => {
        triggerCalculationDebounced();
    });

    // Initial load
    updateLiveCounters();
    requestBackendCalculation();
});

