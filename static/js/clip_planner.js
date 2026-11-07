/**
 * Universal Clip Planning Engine & Narration Segmenter - Client Controller
 * Video Calculator Platform
 */

document.addEventListener('DOMContentLoaded', () => {
    // -----------------------------------------------------------------------
    // DOM Elements
    // -----------------------------------------------------------------------
    const textarea = document.getElementById('narrationText');
    const clearBtn = document.getElementById('clearTextBtn');
    const liveWordPill = document.getElementById('liveWordPill');
    const charCountDisplay = document.getElementById('charCountDisplay');
    const selectedWpmPill = document.getElementById('selectedWpmPill');
    const customSpeedDrawer = document.getElementById('customSpeedDrawer');
    const customWpmInput = document.getElementById('customWpmInput');
    const customSpeedError = document.getElementById('customSpeedError');
    const selectedClipsPill = document.getElementById('selectedClipsPill');

    const clipOptionsList = document.getElementById('clipOptionsList');
    const newCustomDurationInput = document.getElementById('newCustomDurationInput');
    const btnAddCustomDuration = document.getElementById('btnAddCustomDuration');
    const btnSelectAllClips = document.getElementById('btnSelectAllClips');
    const btnClearAllClips = document.getElementById('btnClearAllClips');
    const btnRestoreDefaultClips = document.getElementById('btnRestoreDefaultClips');

    const advancedHeader = document.getElementById('advancedSettingsHeader');
    const advancedBody = document.getElementById('advancedSettingsBody');
    const advancedIcon = document.getElementById('advancedAccordionIcon');
    const prefSentenceBoundary = document.getElementById('prefSentenceBoundary');
    const sentenceToleranceInput = document.getElementById('sentenceToleranceInput');

    const btnCalculate = document.getElementById('btnCalculatePlan');
    const btnResetAll = document.getElementById('btnResetAll');
    const planStatusBadge = document.getElementById('planStatusBadge');
    const errorBanner = document.getElementById('errorBanner');

    // Results elements
    const heroClipCount = document.getElementById('heroClipCount');
    const heroDurationSubtitle = document.getElementById('heroDurationSubtitle');
    const metricNarrationWords = document.getElementById('metricNarrationWords');
    const metricOverallUtil = document.getElementById('metricOverallUtil');
    const metricTotalGenerated = document.getElementById('metricTotalGenerated');
    const metricTotalUnused = document.getElementById('metricTotalUnused');
    const metricAvgWords = document.getElementById('metricAvgWords');
    const metricAvgDuration = document.getElementById('metricAvgDuration');

    const timelineContainer = document.getElementById('timelineContainer');
    const segmentsListContainer = document.getElementById('segmentsListContainer');
    const reconstructedTextView = document.getElementById('reconstructedTextView');
    const integrityBadge = document.getElementById('integrityBadge');
    const plannerToast = document.getElementById('plannerToast');

    const btnCopyPlanJson = document.getElementById('btnCopyPlanJson');
    const btnCopySegmentsText = document.getElementById('btnCopySegmentsText');
    const btnDownloadJson = document.getElementById('btnDownloadJson');
    const btnDownloadCsv = document.getElementById('btnDownloadCsv');

    // -----------------------------------------------------------------------
    // Configuration & State
    // -----------------------------------------------------------------------
    const CALCULATION_API_URL = '/calculators/talking-flyer/clip-planner-test/calculate/';
    const DEBOUNCE_DELAY_MS = 320;
    const MIN_WPM = 60;
    const MAX_WPM = 240;
    const DEFAULT_STANDARD_DURATIONS = [5, 8, 10, 15, 20, 30];

    let currentWpm = 135;
    let debounceTimer = null;
    let latestRequestId = 0;
    let lastCalculatedPlan = null;

    // In-memory options state: [{ duration: int, reserved: float, selected: bool, isCustom: bool }]
    let clipOptionsState = [];

    function initDefaultClipOptions() {
        clipOptionsState = DEFAULT_STANDARD_DURATIONS.map(d => ({
            duration: d,
            reserved: 0.0,
            selected: true,
            isCustom: false,
        }));
    }

    // -----------------------------------------------------------------------
    // CSRF & Utilities
    // -----------------------------------------------------------------------
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

    function showToast(message) {
        if (!plannerToast) return;
        plannerToast.textContent = message;
        plannerToast.classList.add('show');
        setTimeout(() => {
            plannerToast.classList.remove('show');
        }, 2500);
    }

    function countWordsLocally(text) {
        if (!text) return 0;
        const normalized = text.trim().replace(/\s+/g, ' ');
        if (!normalized) return 0;
        return normalized.split(' ').length;
    }

    function updateLiveCounters() {
        const text = textarea.value || '';
        const words = countWordsLocally(text);
        liveWordPill.textContent = `${words} word${words === 1 ? '' : 's'}`;
        charCountDisplay.textContent = `${text.length} character${text.length === 1 ? '' : 's'}`;
    }

    function setStatus(status, text) {
        planStatusBadge.className = 'results-status-badge';
        if (status === 'loading') {
            planStatusBadge.classList.add('status-loading');
            planStatusBadge.textContent = text || 'Calculating...';
        } else if (status === 'error') {
            planStatusBadge.classList.add('status-error');
            planStatusBadge.textContent = text || 'Input Error';
        } else {
            planStatusBadge.classList.add('status-ready');
            planStatusBadge.textContent = text || 'Ready';
        }
    }

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

    // -----------------------------------------------------------------------
    // Speed WPM Resolution
    // -----------------------------------------------------------------------
    function resolveActiveWpm() {
        const selectedRadio = document.querySelector('input[name="speed_preset"]:checked');
        if (!selectedRadio) return currentWpm;

        if (selectedRadio.value === 'custom') {
            const customVal = parseInt(customWpmInput.value, 10);
            if (isNaN(customVal)) {
                customSpeedError.textContent = `Please enter a whole number between ${MIN_WPM} and ${MAX_WPM}.`;
                customSpeedError.style.display = 'block';
                return null;
            }
            if (customVal < MIN_WPM || customVal > MAX_WPM) {
                customSpeedError.textContent = `Speaking speed must be between ${MIN_WPM} and ${MAX_WPM} WPM.`;
                customSpeedError.style.display = 'block';
                return null;
            }
            customSpeedError.style.display = 'none';
            return customVal;
        }

        customSpeedError.style.display = 'none';
        return parseInt(selectedRadio.value, 10);
    }

    // -----------------------------------------------------------------------
    // Clip Options Rendering & Management
    // -----------------------------------------------------------------------
    function renderClipOptions() {
        clipOptionsList.innerHTML = '';
        let activeCount = 0;

        clipOptionsState.forEach((opt, index) => {
            if (opt.selected) activeCount++;

            const row = document.createElement('div');
            row.className = `clip-option-row ${opt.selected ? 'selected' : ''}`;

            // Left: Checkbox + duration label
            const labelGroup = document.createElement('label');
            labelGroup.className = 'clip-option-label-group';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = opt.selected;
            checkbox.dataset.index = index;
            checkbox.addEventListener('change', () => {
                opt.selected = checkbox.checked;
                renderClipOptions();
                triggerCalculationDebounced();
            });

            const durTag = document.createElement('span');
            durTag.className = 'clip-duration-tag';
            durTag.textContent = `${opt.duration}s clip`;

            labelGroup.appendChild(checkbox);
            labelGroup.appendChild(durTag);

            if (opt.isCustom) {
                const customBadge = document.createElement('span');
                customBadge.className = 'badge-pill badge-words';
                customBadge.style.fontSize = '0.7rem';
                customBadge.textContent = 'Custom';
                labelGroup.appendChild(customBadge);
            }

            // Right: Reserved duration input + optional delete button
            const rightControls = document.createElement('div');
            rightControls.style.display = 'flex';
            rightControls.style.alignItems = 'center';
            rightControls.style.gap = '0.5rem';

            const reservedGroup = document.createElement('div');
            reservedGroup.className = 'reserved-input-group';

            const resLabel = document.createElement('span');
            resLabel.textContent = 'Reserved:';

            const resInput = document.createElement('input');
            resInput.type = 'number';
            resInput.className = 'reserved-input-field';
            resInput.min = '0';
            resInput.max = String(Math.max(0, opt.duration - 0.5));
            resInput.step = '0.1';
            resInput.value = opt.reserved.toFixed(1);
            resInput.title = `Reserved duration in seconds (must be less than ${opt.duration}s)`;

            resInput.addEventListener('change', () => {
                let val = parseFloat(resInput.value);
                if (isNaN(val) || val < 0) val = 0.0;
                if (val >= opt.duration) {
                    val = Math.max(0, opt.duration - 0.5);
                    resInput.value = val.toFixed(1);
                }
                opt.reserved = val;
                triggerCalculationDebounced();
            });

            const sUnit = document.createElement('span');
            sUnit.textContent = 's';

            reservedGroup.appendChild(resLabel);
            reservedGroup.appendChild(resInput);
            reservedGroup.appendChild(sUnit);
            rightControls.appendChild(reservedGroup);

            if (opt.isCustom) {
                const btnRemove = document.createElement('button');
                btnRemove.type = 'button';
                btnRemove.className = 'btn-remove-custom';
                btnRemove.title = 'Remove custom option';
                btnRemove.innerHTML = '&times;';
                btnRemove.addEventListener('click', (e) => {
                    e.stopPropagation();
                    clipOptionsState.splice(index, 1);
                    renderClipOptions();
                    triggerCalculationDebounced();
                });
                rightControls.appendChild(btnRemove);
            }

            row.appendChild(labelGroup);
            row.appendChild(rightControls);
            clipOptionsList.appendChild(row);
        });

        selectedClipsPill.textContent = `${activeCount} option${activeCount === 1 ? '' : 's'} active`;
    }

    // -----------------------------------------------------------------------
    // Request Backend Calculation
    // -----------------------------------------------------------------------
    async function requestBackendCalculation() {
        const wpm = resolveActiveWpm();
        if (wpm === null) {
            setStatus('error', 'Invalid WPM');
            return;
        }

        currentWpm = wpm;
        selectedWpmPill.textContent = `${wpm} WPM`;

        const activeOptions = clipOptionsState
            .filter(o => o.selected)
            .map(o => ({
                duration_seconds: o.duration,
                reserved_seconds: o.reserved,
                label: `${o.duration}s`
            }));

        if (activeOptions.length === 0) {
            showError('Please select at least one available clip duration option.');
            return;
        }

        const tolerancePct = parseFloat(sentenceToleranceInput.value) || 20.0;
        const toleranceFrac = Math.max(0.05, Math.min(0.50, tolerancePct / 100.0));

        const payload = {
            narration: textarea.value || '',
            wpm: currentWpm,
            clip_options: activeOptions,
            segmentation: {
                sentence_boundary_preference: prefSentenceBoundary.checked,
                sentence_boundary_tolerance: toleranceFrac,
            }
        };

        showError(null);
        setStatus('loading');
        const requestId = ++latestRequestId;

        try {
            const response = await fetch(CALCULATION_API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });

            if (requestId !== latestRequestId) {
                return;
            }

            const json = await response.json();

            if (!response.ok || !json.success) {
                showError(json.error || 'Server error occurred during clip planning.');
                setStatus('error');
                return;
            }

            lastCalculatedPlan = json;
            renderPlanResults(json);
            setStatus('ready', 'Plan Generated');
        } catch (err) {
            if (requestId === latestRequestId) {
                showError('Network error connecting to planning service.');
                setStatus('error');
            }
        }
    }

    // -----------------------------------------------------------------------
    // Render Results & Segments (Safe DOM Manipulation)
    // -----------------------------------------------------------------------
    function renderPlanResults(data) {
        const plan = data.plan;
        const narration = data.narration;
        const clips = data.clips || [];

        // Summary metrics
        heroClipCount.textContent = plan.clip_count;
        heroDurationSubtitle.textContent =
            `${plan.total_generated_duration_seconds}s generated video (${plan.total_speech_duration_seconds}s speech)`;

        metricNarrationWords.textContent = narration.word_count;
        metricOverallUtil.textContent = plan.overall_utilisation_percentage;
        metricTotalGenerated.textContent = plan.total_generated_duration_seconds;
        metricTotalUnused.textContent = plan.total_unused_duration_seconds;
        metricAvgWords.textContent = plan.average_words_per_clip;
        metricAvgDuration.textContent = plan.average_generated_duration_seconds;

        // Render Visual Clip Timeline
        renderTimeline(clips);

        // Render Individual Segments
        renderSegments(clips);

        // Render Reconstructed Text
        renderReconstruction(clips, data.validation);
    }

    function renderTimeline(clips) {
        timelineContainer.innerHTML = '';

        if (!clips || clips.length === 0) {
            const emptyNotice = document.createElement('span');
            emptyNotice.style.color = 'var(--text-muted)';
            emptyNotice.style.fontSize = '0.85rem';
            emptyNotice.textContent = 'Narration is empty. Enter script to preview visual clip sequence.';
            timelineContainer.appendChild(emptyNotice);
            return;
        }

        clips.forEach((clip, index) => {
            const card = document.createElement('div');
            card.className = 'timeline-clip-card';

            const header = document.createElement('div');
            header.className = 'timeline-clip-header';

            const num = document.createElement('span');
            num.className = 'timeline-clip-num';
            num.textContent = `Clip #${clip.sequence_number}`;

            const dur = document.createElement('span');
            dur.className = 'timeline-clip-dur';
            dur.textContent = `${clip.generated_duration_seconds}s`;

            header.appendChild(num);
            header.appendChild(dur);

            const detail = document.createElement('div');
            detail.className = 'timeline-clip-detail';
            detail.textContent = `${clip.word_count} words (${clip.speech_duration_seconds}s speech)`;

            const range = document.createElement('div');
            range.className = 'timeline-clip-range';
            range.textContent = `Words ${clip.start_word_index}–${clip.end_word_index} (${clip.utilisation_percentage}% util)`;

            // Mini progress bar
            const barBg = document.createElement('div');
            barBg.className = 'timeline-progress-bar-bg';

            const utilPct = parseFloat(clip.utilisation_percentage) || 0;
            const fillSpeech = document.createElement('div');
            fillSpeech.className = 'timeline-progress-fill-speech';
            fillSpeech.style.width = `${Math.min(100, utilPct)}%`;

            const fillUnused = document.createElement('div');
            fillUnused.className = 'timeline-progress-fill-unused';
            fillUnused.style.width = `${Math.max(0, 100 - utilPct)}%`;

            barBg.appendChild(fillSpeech);
            barBg.appendChild(fillUnused);

            card.appendChild(header);
            card.appendChild(detail);
            card.appendChild(range);
            card.appendChild(barBg);
            timelineContainer.appendChild(card);

            if (index < clips.length - 1) {
                const arrow = document.createElement('div');
                arrow.className = 'timeline-arrow';
                arrow.innerHTML = '&rarr;';
                timelineContainer.appendChild(arrow);
            }
        });
    }

    function renderSegments(clips) {
        segmentsListContainer.innerHTML = '';

        if (!clips || clips.length === 0) {
            const emptyNotice = document.createElement('div');
            emptyNotice.style.padding = '1.5rem';
            emptyNotice.style.textAlign = 'center';
            emptyNotice.style.color = 'var(--text-muted)';
            emptyNotice.style.fontSize = '0.9rem';
            emptyNotice.textContent = 'No clips generated yet.';
            segmentsListContainer.appendChild(emptyNotice);
            return;
        }

        clips.forEach((clip) => {
            const card = document.createElement('div');
            card.className = 'segment-card';

            // Card Header
            const header = document.createElement('div');
            header.className = 'segment-card-header';

            const title = document.createElement('div');
            title.className = 'segment-card-title';
            title.textContent = `Clip ${clip.sequence_number} (${clip.generated_duration_seconds}s video)`;

            const badges = document.createElement('div');
            badges.className = 'segment-card-badges';

            const wordsBadge = document.createElement('span');
            wordsBadge.className = 'badge-pill badge-words';
            wordsBadge.textContent = `${clip.word_count} words (range: ${clip.start_word_index}–${clip.end_word_index})`;

            const timeBadge = document.createElement('span');
            timeBadge.className = 'badge-pill badge-time';
            timeBadge.textContent = `${clip.speech_duration_seconds}s speech`;

            badges.appendChild(wordsBadge);
            badges.appendChild(timeBadge);
            header.appendChild(title);
            header.appendChild(badges);

            // Card Body
            const body = document.createElement('div');
            body.className = 'segment-card-body';

            const quote = document.createElement('div');
            quote.className = 'segment-narration-quote';
            quote.textContent = clip.narration_text; // Safe text insertion
            body.appendChild(quote);

            const miniGrid = document.createElement('div');
            miniGrid.className = 'segment-metrics-mini-grid';

            const m1 = document.createElement('div');
            m1.textContent = `Reserved: ${clip.reserved_duration_seconds}s`;

            const m2 = document.createElement('div');
            m2.textContent = `Usable: ${clip.usable_narration_duration_seconds}s`;

            const m3 = document.createElement('div');
            m3.textContent = `Unused Video: ${clip.unused_generated_duration_seconds}s`;

            const m4 = document.createElement('div');
            m4.textContent = `Utilisation: ${clip.utilisation_percentage}%`;

            miniGrid.appendChild(m1);
            miniGrid.appendChild(m2);
            miniGrid.appendChild(m3);
            miniGrid.appendChild(m4);
            body.appendChild(miniGrid);

            // Card Footer
            const footer = document.createElement('div');
            footer.className = 'segment-card-footer';

            const btnCopyClip = document.createElement('button');
            btnCopyClip.type = 'button';
            btnCopyClip.className = 'btn-copy-clip';
            btnCopyClip.textContent = '📋 Copy Segment';
            btnCopyClip.addEventListener('click', () => {
                navigator.clipboard.writeText(clip.narration_text)
                    .then(() => showToast(`Copied segment for Clip #${clip.sequence_number}!`))
                    .catch(() => showToast('Failed to copy text.'));
            });

            footer.appendChild(btnCopyClip);

            card.appendChild(header);
            card.appendChild(body);
            card.appendChild(footer);
            segmentsListContainer.appendChild(card);
        });
    }

    function renderReconstruction(clips, validation) {
        if (!clips || clips.length === 0) {
            reconstructedTextView.textContent = '(Reconstructed script will appear here once planned)';
            integrityBadge.style.display = 'none';
            return;
        }

        const fullText = clips.map(c => c.narration_text).join(' ');
        reconstructedTextView.textContent = fullText;

        if (validation && validation.is_valid) {
            integrityBadge.style.display = 'inline-block';
            integrityBadge.className = 'results-status-badge status-ready';
            integrityBadge.textContent = '100% Integrity Verified';
        } else {
            integrityBadge.style.display = 'inline-block';
            integrityBadge.className = 'results-status-badge status-error';
            integrityBadge.textContent = 'Integrity Mismatch';
        }
    }

    function triggerCalculationDebounced() {
        updateLiveCounters();
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(() => {
            requestBackendCalculation();
        }, DEBOUNCE_DELAY_MS);
    }

    // -----------------------------------------------------------------------
    // Export Functions
    // -----------------------------------------------------------------------
    function handleCopyPlanJson() {
        if (!lastCalculatedPlan) {
            showToast('No calculated plan to copy.');
            return;
        }
        const jsonStr = JSON.stringify(lastCalculatedPlan, null, 2);
        navigator.clipboard.writeText(jsonStr)
            .then(() => showToast('Complete plan JSON copied to clipboard!'))
            .catch(() => showToast('Clipboard write failed.'));
    }

    function handleCopySegmentsText() {
        if (!lastCalculatedPlan || !lastCalculatedPlan.clips || lastCalculatedPlan.clips.length === 0) {
            showToast('No script segments to copy.');
            return;
        }
        const lines = lastCalculatedPlan.clips.map(c =>
            `Clip ${c.sequence_number} (${c.generated_duration_seconds}s, words ${c.start_word_index}–${c.end_word_index}):\n${c.narration_text}`
        );
        const fullScript = lines.join('\n\n');
        navigator.clipboard.writeText(fullScript)
            .then(() => showToast('Script segments copied to clipboard!'))
            .catch(() => showToast('Clipboard write failed.'));
    }

    function handleDownloadJson() {
        if (!lastCalculatedPlan) {
            showToast('No calculated plan to download.');
            return;
        }
        const jsonStr = JSON.stringify(lastCalculatedPlan, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `clip_plan_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('JSON plan downloaded.');
    }

    function handleDownloadCsv() {
        if (!lastCalculatedPlan || !lastCalculatedPlan.clips || lastCalculatedPlan.clips.length === 0) {
            showToast('No clips to download in CSV.');
            return;
        }

        const headers = [
            'Clip Number',
            'Generated Duration (s)',
            'Reserved Duration (s)',
            'Usable Narration Duration (s)',
            'Word Count',
            'Starting Word',
            'Ending Word',
            'Narration Segment',
            'Speech Duration (s)',
            'Unused Duration (s)',
            'Utilisation (%)'
        ];

        const escapeCsv = (str) => {
            const val = String(str == null ? '' : str);
            if (val.includes(',') || val.includes('"') || val.includes('\n') || val.includes('\r')) {
                return `"${val.replace(/"/g, '""')}"`;
            }
            return val;
        };

        const rows = [headers.join(',')];

        lastCalculatedPlan.clips.forEach(c => {
            const row = [
                c.sequence_number,
                c.generated_duration_seconds,
                c.reserved_duration_seconds,
                c.usable_narration_duration_seconds,
                c.word_count,
                c.start_word_index,
                c.end_word_index,
                escapeCsv(c.narration_text),
                c.speech_duration_seconds,
                c.unused_generated_duration_seconds,
                c.utilisation_percentage
            ];
            rows.push(row.join(','));
        });

        const csvContent = '\uFEFF' + rows.join('\r\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `clip_plan_breakdown_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('CSV breakdown downloaded.');
    }

    // -----------------------------------------------------------------------
    // Reset Action
    // -----------------------------------------------------------------------
    function handleResetAll() {
        textarea.value = '';
        currentWpm = 135;

        // Reset speed radio
        const convRadio = document.querySelector('input[name="speed_preset"][value="135"]');
        if (convRadio) {
            convRadio.checked = true;
            document.querySelectorAll('.speed-option-label').forEach(l => l.classList.remove('active'));
            const parentLabel = convRadio.closest('.speed-option-label');
            if (parentLabel) parentLabel.classList.add('active');
        }
        customSpeedDrawer.classList.add('hidden');
        customSpeedError.style.display = 'none';
        selectedWpmPill.textContent = '135 WPM';

        // Reset clip options
        initDefaultClipOptions();
        renderClipOptions();

        // Reset advanced settings
        prefSentenceBoundary.checked = true;
        sentenceToleranceInput.value = '20';

        updateLiveCounters();
        requestBackendCalculation();
        showToast('Calculator reset to defaults.');
    }

    // -----------------------------------------------------------------------
    // Event Listeners
    // -----------------------------------------------------------------------
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
                customSpeedDrawer.classList.remove('hidden');
                customWpmInput.focus();
                if (!customWpmInput.value) {
                    customWpmInput.value = currentWpm || 140;
                }
            } else {
                customSpeedDrawer.classList.add('hidden');
                customSpeedError.style.display = 'none';
            }

            requestBackendCalculation();
        });
    });

    customWpmInput.addEventListener('input', () => {
        triggerCalculationDebounced();
    });

    // Durations toolbar
    btnSelectAllClips.addEventListener('click', () => {
        clipOptionsState.forEach(o => o.selected = true);
        renderClipOptions();
        triggerCalculationDebounced();
    });

    btnClearAllClips.addEventListener('click', () => {
        clipOptionsState.forEach(o => o.selected = false);
        renderClipOptions();
        triggerCalculationDebounced();
    });

    btnRestoreDefaultClips.addEventListener('click', () => {
        initDefaultClipOptions();
        renderClipOptions();
        triggerCalculationDebounced();
    });

    // Add custom duration
    btnAddCustomDuration.addEventListener('click', () => {
        const val = parseInt(newCustomDurationInput.value, 10);
        if (isNaN(val) || val < 1 || val > 600) {
            showToast('Please enter a valid whole duration between 1 and 600 seconds.');
            return;
        }

        // Check if identical duration and 0 reserved already exists
        const exists = clipOptionsState.some(o => o.duration === val && o.reserved === 0);
        if (exists) {
            showToast(`Option for ${val}s already exists.`);
            return;
        }

        clipOptionsState.push({
            duration: val,
            reserved: 0.0,
            selected: true,
            isCustom: true,
        });

        // Keep sorted descending by duration
        clipOptionsState.sort((a, b) => b.duration - a.duration);

        newCustomDurationInput.value = '';
        renderClipOptions();
        triggerCalculationDebounced();
        showToast(`Added ${val}s custom clip option.`);
    });

    // Advanced settings accordion
    advancedHeader.addEventListener('click', () => {
        const isHidden = advancedBody.classList.contains('hidden');
        if (isHidden) {
            advancedBody.classList.remove('hidden');
            advancedIcon.innerHTML = '&minus;';
            advancedHeader.setAttribute('aria-expanded', 'true');
        } else {
            advancedBody.classList.add('hidden');
            advancedIcon.innerHTML = '&plus;';
            advancedHeader.setAttribute('aria-expanded', 'false');
        }
    });

    prefSentenceBoundary.addEventListener('change', triggerCalculationDebounced);
    sentenceToleranceInput.addEventListener('change', triggerCalculationDebounced);

    // Primary action buttons
    btnCalculate.addEventListener('click', () => {
        requestBackendCalculation();
    });

    btnResetAll.addEventListener('click', handleResetAll);

    // Export buttons
    btnCopyPlanJson.addEventListener('click', handleCopyPlanJson);
    btnCopySegmentsText.addEventListener('click', handleCopySegmentsText);
    btnDownloadJson.addEventListener('click', handleDownloadJson);
    btnDownloadCsv.addEventListener('click', handleDownloadCsv);

    // -----------------------------------------------------------------------
    // Initial Load
    // -----------------------------------------------------------------------
    initDefaultClipOptions();
    renderClipOptions();
    updateLiveCounters();
    requestBackendCalculation();
});

