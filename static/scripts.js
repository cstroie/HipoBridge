marked.use({ breaks: true });

const APP_TITLE = 'HippoBridge';
function setPageTitle(prefix) {
    document.title = prefix ? `${prefix} — ${APP_TITLE}` : APP_TITLE;
}

function localDateStr(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

document.addEventListener('DOMContentLoaded', function() {
    // Schedule tab state — declared early since the initial tab switch on
    // page load can call fetchScheduleFromInputs synchronously, before a
    // `let` declared later in this scope would be initialized (TDZ).
    // Multi-select: empty set means "All" (no filter), same as before when
    // this was a single empty string.
    let activeScheduleStatusFilter = new Set();

    // DOM Elements - Cache selectors for better performance
    const elements = {
        form: document.getElementById('cnpForm'),
        cnpInput: document.getElementById('cnpInput'),
        analyzeBtn: document.getElementById('analyzeBtn'),
        errorDiv: document.getElementById('error'),
        navItems: document.querySelectorAll('.nav-item'),
        tabContents: document.querySelectorAll('.tab-content'),
        // Patient tab elements
        patientId: document.getElementById('patientId'),
        patientName: document.getElementById('patientName'),
        patientNameInfo: document.getElementById('patientNameInfo'),
        patientAgeInfo: document.getElementById('patientAgeInfo'),
        patientCnp: document.getElementById('patientCnp'),
        patientGender: document.getElementById('patientGender'),
        patientDiagnosis: document.getElementById('patientDiagnosis'),
        refreshPatientBtn: document.getElementById('refreshPatientBtn'),
        patientBirthDate: document.getElementById('patientBirthDate'),
        patientPhone: document.getElementById('patientPhone'),
        patientEmail: document.getElementById('patientEmail'),
        patientAddress: document.getElementById('patientAddress'),
        qrPanel:          document.getElementById('patientQrPanel'),
        qrLastName:       document.getElementById('qrLastName'),
        qrFirstName:      document.getElementById('qrFirstName'),
        qrCnp:            document.getElementById('qrCnp'),
        qrBirthDate:      document.getElementById('qrBirthDate'),
        qrLabelLastName:  document.getElementById('qrLabelLastName'),
        qrLabelFirstName: document.getElementById('qrLabelFirstName'),
        qrLabelCnp:       document.getElementById('qrLabelCnp'),
        qrLabelBirthDate: document.getElementById('qrLabelBirthDate'),
        navPatientLabel: document.getElementById('navPatientLabel'),
        navPatientGroup: document.getElementById('navPatientGroup'),
        historyList: document.getElementById('historyList'),
        historyLoading: document.getElementById('historyLoading'),
        historyEmpty: document.getElementById('historyEmpty'),
        presentationsCount: document.getElementById('presentationsCount'),
        checkinsCount: document.getElementById('checkinsCount'),
        checkoutsCount: document.getElementById('checkoutsCount'),
        imagingCount: document.getElementById('imagingCount'),
        labCount: document.getElementById('labCount'),
        // Imaging tab elements
        imagingGrid: document.getElementById('imagingGrid'),
        imagingNoData: document.getElementById('imagingNoData'),
        imagingEyebrow: document.getElementById('imagingEyebrow'),
        imagingFilter: document.getElementById('imagingFilter'),
        // Laboratory tab elements
        labGrid: document.getElementById('labGrid'),
        labNoData: document.getElementById('labNoData'),
        labEyebrow: document.getElementById('labEyebrow'),
        labFilter: document.getElementById('labFilter'),
        trendsSection: document.getElementById('trendsSection'),
        trendsContainer: document.getElementById('trendsContainer'),
        trendsSubtitle: document.getElementById('trendsSubtitle'),
        // Epicrisis tab elements
        epicrisisContent: document.getElementById('epicrisisContent'),
        epicrisisNoData:  document.getElementById('epicrisisNoData'),
        copyEpicrisisBtn: document.getElementById('copyEpicrisisBtn'),
        // Report tab elements
        reportCard: document.getElementById('reportCard'),
        patientReportMarkdown: document.getElementById('patientReportMarkdown'),
        patientReportBlocks: document.getElementById('patientReportBlocks'),
        copyReportBtn: document.getElementById('copyReportBtn'),
        aiReportBtn: document.getElementById('aiReportBtn'),
        aiLabBtn: document.getElementById('aiLabBtn'),
        copyLabBtn: document.getElementById('copyLabBtn'),
        contrastSafetyBtn: document.getElementById('contrastSafetyBtn'),
        // AI tab elements
        aiPreExamToolbar: document.getElementById('aiPreExamToolbar'),
        aiPreExamAnchor: document.getElementById('aiPreExamAnchor'),
        aiEmptyState: document.getElementById('aiEmptyState'),
        // Patient profile "AI Summary" panel
        patientAiSummaryBtn: document.getElementById('patientAiSummaryBtn'),
        patientAiSummaryAnchor: document.getElementById('patientAiSummaryAnchor'),
        // Header elements
        quickSearch: document.getElementById('quickSearch'),
        quickSearchBtn: document.getElementById('quickSearchBtn'),
        themeToggle: document.getElementById('themeToggle'),
        userButton: document.getElementById('userButton'),
        // Search examples
        clearRecentBtn: document.getElementById('clearRecentBtn'),
        recentEmpty: document.getElementById('recentEmpty'),
        // Patient actions
        // Epicrisis actions
        // Loading overlay
        loadingOverlay: document.getElementById('loadingOverlay'),
        loadingSpinner: document.getElementById('loadingSpinner'),
        loadingStep: document.getElementById('loadingStep'),
        loadingError: document.getElementById('loadingError'),
        loadingErrorMsg: document.getElementById('loadingErrorMsg'),
        loadingErrorDismiss: document.getElementById('loadingErrorDismiss'),
        // Recent searches
        recentSearchesList: document.getElementById('recentSearchesList'),
        // Clinical text search (epicrisis/imaging report text)
        clinicalSearchInput: document.getElementById('clinicalSearchInput'),
        clinicalSearchResults: document.getElementById('clinicalSearchResults'),
        clinicalSearchEmpty: document.getElementById('clinicalSearchEmpty'),
        clinicalSearchDisabled: document.getElementById('clinicalSearchDisabled'),
        // Schedule tab elements
        scheduleStartDate: document.getElementById('scheduleStartDate'),
        scheduleEndDate: document.getElementById('scheduleEndDate'),
        refreshScheduleBtn: document.getElementById('refreshScheduleBtn'),
        scheduleMdBtn: document.getElementById('scheduleMdBtn'),
        scheduleMdPanel: document.getElementById('scheduleMdPanel'),
        scheduleMdBody: document.getElementById('scheduleMdBody'),
        scheduleMdTitle: document.getElementById('scheduleMdTitle'),
        scheduleMdSub: document.getElementById('scheduleMdSub'),
        scheduleMdPrintBtn: document.getElementById('scheduleMdPrintBtn'),
        scheduleMdAiBtn: document.getElementById('scheduleMdAiBtn'),
        scheduleMdCopyBtn: document.getElementById('scheduleMdCopyBtn'),
        schedulePatientFilter: document.getElementById('schedulePatientFilter'),
        scheduleLabFilter:     document.getElementById('scheduleLabFilter'),
        scheduleSectionFilter: document.getElementById('scheduleSectionFilter'),
        scheduleLimitSelect:   document.getElementById('scheduleLimitSelect'),
        scheduleTable: document.getElementById('scheduleTable'),
        scheduleBody: document.getElementById('scheduleBody'),
        noSchedule: document.getElementById('noSchedule'),
        scheduleTimeline: document.getElementById('scheduleTimeline'),
        scheduleStatusChips: document.getElementById('scheduleStatusChips'),
        scheduleClearFiltersBtn: document.getElementById('scheduleClearFiltersBtn'),
        scheduleHero: document.getElementById('scheduleHero'),
        scheduleDayMetrics: document.getElementById('scheduleDayMetrics'),
        scheduleModBars: document.getElementById('scheduleModBars')
    };
    
    // Bounded in-memory cache (100 entries per store; evicts oldest on overflow)
    const CACHE_MAX = 100;
    const cache = { encounters: {}, reports: {} };
    function cachePut(store, key, value) {
        const keys = Object.keys(store);
        if (keys.length >= CACHE_MAX) delete store[keys[0]];
        store[key] = value;
    }

    // debug logging helper (set DEBUG=true during development to see logs)
    const DEBUG = false;
    function log(...args) { if (DEBUG) console.log(...args); }

    function debounce(fn, ms) {
        let timer;
        return function(...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), ms); };
    }

    // ── Credential storage ────────────────────────────────────────────
    const CRED_KEY = 'hb_creds';

    function getCredentials() {
        const raw = sessionStorage.getItem(CRED_KEY);
        return raw ? JSON.parse(raw) : null;
    }

    function setCredentials(username, password) {
        sessionStorage.setItem(CRED_KEY, JSON.stringify({ username, password }));
    }

    function clearCredentials() {
        sessionStorage.removeItem(CRED_KEY);
        localStorage.removeItem('hipocrateUrl');
        hipocrateUrl = null;
    }

    function authHeader() {
        const creds = getCredentials();
        if (!creds) return {};
        return { 'Authorization': 'Basic ' + btoa(`${creds.username}:${creds.password}`) };
    }

    // Wrapper around fetch() that injects auth and handles 401 by re-showing login dialog
    async function apiFetch(url, options = {}) {
        const headers = { ...authHeader(), ...(options.headers || {}) };
        const resp = await fetch(url, { ...options, headers });
        if (resp.status === 401) {
            clearCredentials();
            stopScheduleAutoRefresh();
            showLoginDialog('Session expired or wrong credentials. Please sign in again.');
            throw new Error('Authentication required');
        }
        return resp;
    }

    // ── Schedule periodic auto-refresh ────────────────────────────────
    // Once authenticated, keep the schedule current (and warm the
    // idle-prefetch cache for new items) by refetching, starting at every
    // 5 minutes and backing off by 1.2x each tick up to a 15-minute cap.
    // A manual refresh resets the interval back to 5 minutes.
    let scheduleAutoRefreshTimer = null;
    let scheduleAutoRefreshInterval = 0;
    const SCHEDULE_AUTO_REFRESH_INTERVAL_MIN = 5 * 60 * 1000;
    const SCHEDULE_AUTO_REFRESH_INTERVAL_MAX = 15 * 60 * 1000;
    const SCHEDULE_AUTO_REFRESH_BACKOFF = 1.2;

    function scheduleNextAutoRefresh() {
        scheduleAutoRefreshTimer = setTimeout(() => {
            fetchScheduleFromInputs(true);
            scheduleAutoRefreshInterval = Math.min(
                scheduleAutoRefreshInterval * SCHEDULE_AUTO_REFRESH_BACKOFF,
                SCHEDULE_AUTO_REFRESH_INTERVAL_MAX
            );
            scheduleNextAutoRefresh();
        }, scheduleAutoRefreshInterval);
    }

    function startScheduleAutoRefresh(reset = false) {
        if (scheduleAutoRefreshTimer && !reset) return;
        clearTimeout(scheduleAutoRefreshTimer);
        scheduleAutoRefreshInterval = SCHEDULE_AUTO_REFRESH_INTERVAL_MIN;
        scheduleNextAutoRefresh();
    }

    function stopScheduleAutoRefresh() {
        clearTimeout(scheduleAutoRefreshTimer);
        scheduleAutoRefreshTimer = null;
    }

    // ── Login dialog ──────────────────────────────────────────────────
    const loginDialog = document.getElementById('loginDialog');
    const loginForm   = document.getElementById('loginForm');
    const loginError  = document.getElementById('loginError');
    const loginMsg    = document.getElementById('loginDialogMessage');

    function showLoginDialog(message = '') {
        loginMsg.textContent = message;
        loginError.hidden = true;
        loginError.textContent = '';
        document.getElementById('loginUsername').value = getCredentials()?.username || '';
        document.getElementById('loginPassword').value = '';
        loginDialog.showModal();
        // Focus password if username already filled
        const target = document.getElementById('loginUsername').value
            ? document.getElementById('loginPassword')
            : document.getElementById('loginUsername');
        target.focus();
    }

    loginForm.addEventListener('submit', async e => {
        e.preventDefault();
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value;
        const submitBtn = document.getElementById('loginSubmitBtn');

        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing in…';
        loginError.hidden = true;

        // Validate against /api/whoami
        try {
            const resp = await fetch('/api/whoami', {
                headers: { 'Authorization': 'Basic ' + btoa(`${username}:${password}`) }
            });
            if (resp.status === 401) {
                loginError.textContent = 'Wrong username or password.';
                loginError.hidden = false;
                document.getElementById('loginPassword').focus();
                return;
            }
            // Any non-401 response means Hipocrate accepted the credentials
            setCredentials(username, password);
            whoamiData = null; // reset cached whoami so it re-fetches with new creds
            whoamiReady = fetchWhoami().catch(() => {});
            loginDialog.close();
            // Trigger the initial schedule load now that we have credentials
            fetchScheduleFromInputs();
            startScheduleAutoRefresh();
        } catch (err) {
            loginError.textContent = `Network error: ${err.message}`;
            loginError.hidden = false;
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Sign in';
        }
    });

    // limit for simultaneous network requests (helpful when handling many IDs)
    const MAX_CONCURRENT_REQUESTS = 5;

    /**
     * Map over an array with a concurrency limit.
     * @param {Array} arr
     * @param {number} limit
     * @param {Function} asyncFn - receives (item, index) and returns a promise
     * @returns {Promise<Array>} results in original order
     */
    async function limitedMap(arr, limit, asyncFn) {
        const results = new Array(arr.length);
        let idx = 0;
        async function worker() {
            while (idx < arr.length) {
                const current = idx++;
                try {
                    results[current] = await asyncFn(arr[current], current);
                } catch (err) {
                    results[current] = null;
                }
            }
        }
        const workers = [];
        for (let i = 0; i < limit; i++) workers.push(worker());
        await Promise.all(workers);
        return results;
    }

    let whoamiReady = Promise.resolve();

    // Pre-exam toolbar: each button sends the same clinical text
    // (getPatientClinicalText()) under a different `kind`, so the
    // radiologist can generate multiple prompt styles for the same record.
    // Only 'pre_exam_brief' has a working prompt today — the rest are
    // scaffolded ahead of their prompts landing in llm/prompts/ (drafts
    // collected in llm/prompts/drafts/ in the meantime); clicking one of
    // those surfaces the backend's existing "unknown summary kind" error
    // until its PROMPT_META entry + <kind>.md exist. Icons are chosen from
    // the existing self-hosted Font Awesome subset (static/fontawesome.css)
    // — adding a new glyph needs a separate subsetting step.
    // Declared here (ahead of initApp() below) rather than near
    // buildAiPreExamToolbar() further down: it's a `const`, not a hoisted
    // `function`, and initApp() runs synchronously as soon as this script
    // executes — a `const` declared after that call site is still in its
    // temporal dead zone when buildAiPreExamToolbar() (called from inside
    // initApp() -> initEventListeners()) tries to read it.
    const PRE_EXAM_TOOLBAR = [
        { kind: 'pre_exam_oneliner',  label: 'One-liner',         icon: 'fa-bolt' },
        { kind: 'pre_exam_brief',     label: 'Brief',             icon: 'fa-wand-magic-sparkles' },
        { kind: 'pre_exam_executive', label: 'Executive summary', icon: 'fa-notes-medical' },
        { kind: 'pre_exam_soap',      label: 'SOAP',              icon: 'fa-file-medical' },
    ];

    // Generation counter for the on-demand schedule exam list; must be declared
    // before initApp() runs (fetchSchedule -> buildScheduleMarkdown uses it).
    let scheduleMdRun = 0;
    const scheduleMdState = { rows: [], els: [] };

    // Initialize application
    initApp();
    
    function initApp() {
        // Initialize theme
        initTheme();

        // Initialize tabs
        initializeTabs();

        // Browser session/bfcache restore can reapply stale date values after
        // load — force the schedule range back to its default on restore.
        window.addEventListener('pageshow', e => {
            if (!e.persisted) return;
            const today = localDateStr();
            const yesterday = localDateStr(new Date(Date.now() - 86400000));
            if (elements.scheduleStartDate) elements.scheduleStartDate.value = yesterday;
            if (elements.scheduleEndDate)   elements.scheduleEndDate.value   = today;
        });

        // Initialize event listeners
        initEventListeners();

        // Load recent searches
        loadRecentSearches();

        // Reveal header and active tab now that JS is ready
        const appBar = document.querySelector('.app-bar');
        if (appBar) { appBar.removeAttribute('hidden'); appBar.style.display = ''; }

        // Show login dialog if no credentials are stored
        if (!getCredentials()) {
            showLoginDialog();
        } else {
            whoamiReady = fetchWhoami().catch(() => {});
            startScheduleAutoRefresh();
        }
    }
    
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'auto';
        document.documentElement.setAttribute('data-theme', savedTheme);
        const themeIcon = elements.themeToggle?.querySelector('i');
        if (themeIcon) themeIcon.className = savedTheme === 'dark' ? 'fas fa-sun' : savedTheme === 'light' ? 'fas fa-moon' : 'fas fa-circle-half-stroke';
    }
    
    function initializeTabs() {
        // Set schedule date defaults before switchTab triggers the first fetch
        const today = localDateStr();
        const yesterday = localDateStr(new Date(Date.now() - 86400000));
        if (elements.scheduleStartDate) elements.scheduleStartDate.value = yesterday;
        if (elements.scheduleEndDate)   elements.scheduleEndDate.value   = today;

        elements.tabContents.forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });

        // Honour the URL fragment, but only for tabs available without a
        // loaded patient; patient-scoped tabs fall back to the default
        const hash = location.hash.replace('#', '');
        switchTab(['schedule', 'search'].includes(hash) ? hash : 'search');
    }
    
    function initEventListeners() {
        // Tab navigation
        elements.navItems.forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                switchTab(this.getAttribute('data-tab'));
            });
        });
        
        // Form submission
        elements.form.addEventListener('submit', handleFormSubmit);
        
        // Quick search
        if (elements.quickSearchBtn) {
            elements.quickSearchBtn.addEventListener('click', function() {
                const query = elements.quickSearch.value.trim();
                if (query) {
                    elements.cnpInput.value = query;
                    elements.form.dispatchEvent(new Event('submit'));
                }
            });
        }
        
        // Quick search enter key
        if (elements.quickSearch) {
            elements.quickSearch.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    elements.quickSearchBtn.click();
                }
            });
        }
        
        // Theme toggle
        if (elements.themeToggle) {
            elements.themeToggle.addEventListener('click', toggleTheme);
        }

        // User account button
        if (elements.userButton) {
            elements.userButton.addEventListener('click', showUserModal);
        }

        
        // Clear recent searches
        if (elements.clearRecentBtn) {
            elements.clearRecentBtn.addEventListener('click', clearRecentSearches);
        }

        // Clinical text search (epicrisis/imaging report text already indexed
        // server-side — see search.py). Debounced like the schedule
        // patient-name filter above.
        if (elements.clinicalSearchInput) {
            const debouncedClinicalSearch = debounce(runClinicalSearch, 400);
            elements.clinicalSearchInput.addEventListener('input', debouncedClinicalSearch);
        }

        // Stat pills that navigate to their tab
        document.querySelectorAll('.stat-pill-link').forEach(pill => {
            pill.addEventListener('click', () => switchTab(pill.dataset.goto));
        });

        // Imaging and lab filter selects
        if (elements.imagingFilter) {
            elements.imagingFilter.addEventListener('change', () =>
                filterGrid(elements.imagingGrid, elements.imagingNoData, elements.imagingFilter.value));
        }

        
        // Epicrisis tab buttons
        if (elements.copyEpicrisisBtn) {
            elements.copyEpicrisisBtn.addEventListener('click', copyEpicrisisMarkdown);
        }

        // Report tab buttons
        if (elements.copyReportBtn) {
            elements.copyReportBtn.addEventListener('click', copyReportMarkdown);
        }
        if (elements.copyLabBtn) {
            elements.copyLabBtn.addEventListener('click', copyLabMarkdown);
        }

        // Profile tab: click CNP / Name to copy them to the clipboard
        if (elements.patientCnp) {
            elements.patientCnp.style.cursor = 'pointer';
            elements.patientCnp.addEventListener('click', () => copyTextToClipboard(elements.patientCnp.textContent));
        }
        if (elements.patientNameInfo) {
            elements.patientNameInfo.style.cursor = 'pointer';
            elements.patientNameInfo.addEventListener('click', () => copyTextToClipboard(elements.patientNameInfo.textContent));
        }

        // AI summary buttons (report header, lab trends, pre-exam tab).
        // Per-card buttons (epicrisis, imaging) are wired at render time.
        wireAiButton(elements.aiReportBtn, 'report',
            () => elements.reportCard, () => getPatientClinicalText());
        if (elements.aiLabBtn) elements.aiLabBtn.addEventListener('click', runLabSummary);
        if (elements.contrastSafetyBtn) elements.contrastSafetyBtn.addEventListener('click', runContrastSafetyCheck);
        elements.aiPreExamBtns = buildAiPreExamToolbar();
        if (elements.patientAiSummaryBtn) {
            elements.patientAiSummaryBtn.addEventListener('click', generatePatientAiSummary);
        }

        // Schedule tab
        {
            if (elements.scheduleStartDate) {
                elements.scheduleStartDate.addEventListener('change', fetchScheduleFromInputs);
            }
            if (elements.scheduleEndDate) {
                elements.scheduleEndDate.addEventListener('change', fetchScheduleFromInputs);
            }
        }
        if (elements.loadingErrorDismiss) {
            elements.loadingErrorDismiss.addEventListener('click', hideLoading);
        }
        if (elements.refreshScheduleBtn) {
            elements.refreshScheduleBtn.addEventListener('click', () => {
                fetchScheduleFromInputs(true);
                if (scheduleAutoRefreshTimer) startScheduleAutoRefresh(true);
                triggerPacsRefresh();
            });
        }
        if (elements.scheduleMdBtn) {
            elements.scheduleMdBtn.addEventListener('click', () => buildScheduleMarkdown());
        }
        if (elements.scheduleMdAiBtn) {
            elements.scheduleMdAiBtn.addEventListener('click', summarizeScheduleMdReports);
        }
        if (elements.scheduleMdPrintBtn) {
            elements.scheduleMdPrintBtn.addEventListener('click', () => {
                document.body.classList.add('print-exam-list');
                window.print();
            });
            window.addEventListener('afterprint', () => document.body.classList.remove('print-exam-list'));
        }
        if (elements.scheduleMdCopyBtn) {
            elements.scheduleMdCopyBtn.addEventListener('click', () =>
                copyMarkdown(elements.scheduleMdPanel, elements.scheduleMdCopyBtn,
                    () => flashIcon(elements.scheduleMdCopyBtn)));
        }
        if (elements.refreshPatientBtn) {
            elements.refreshPatientBtn.addEventListener('click', refreshCurrentPatient);
        }
        if (elements.schedulePatientFilter) {
            const debouncedScheduleFetch = debounce(() => fetchScheduleFromInputs(), 400);
            elements.schedulePatientFilter.addEventListener('input', debouncedScheduleFetch);
        }
        if (elements.scheduleLabFilter) {
            elements.scheduleLabFilter.addEventListener('change', fetchScheduleFromInputs);
        }
        if (elements.scheduleSectionFilter) {
            elements.scheduleSectionFilter.addEventListener('change', fetchScheduleFromInputs);
        }
        if (elements.scheduleLimitSelect) {
            elements.scheduleLimitSelect.addEventListener('change', fetchScheduleFromInputs);
        }
        if (elements.scheduleClearFiltersBtn) {
            elements.scheduleClearFiltersBtn.addEventListener('click', clearScheduleFilters);
        }

        // Imaging chips — delegated so it works regardless of when chips render
        document.getElementById('imagingChips')?.addEventListener('click', e => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            document.querySelectorAll('#imagingChips .chip').forEach(c => c.classList.remove('chip-active'));
            chip.classList.add('chip-active');
            if (elements.imagingFilter) {
                elements.imagingFilter.value = chip.dataset.filter || 'all';
                elements.imagingFilter.dispatchEvent(new Event('change'));
            }
        });

        // Lab chips — delegated to cover dynamically-added section chips
        document.getElementById('labChips')?.addEventListener('click', e => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            document.querySelectorAll('#labChips .chip').forEach(c => c.classList.remove('chip-active'));
            chip.classList.add('chip-active');
            filterLabGrid(chip.dataset.filter || 'all');
        });

        // Schedule status chips — multi-select: clicking a status chip toggles
        // it independently so e.g. "In lab" and "In progress" can both be
        // active at once. "All" is a special case, mutually exclusive with
        // every specific status: picking it clears the others, and picking
        // any specific status turns "All" off. Selecting nothing is treated
        // the same as "All" (no filter) — the chip is just re-activated to
        // keep the UI from showing zero active chips.
        elements.scheduleStatusChips?.addEventListener('click', e => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            const allChip = elements.scheduleStatusChips.querySelector('.chip[data-status=""]');
            if (chip === allChip) {
                activeScheduleStatusFilter.clear();
            } else if (activeScheduleStatusFilter.has(chip.dataset.status)) {
                activeScheduleStatusFilter.delete(chip.dataset.status);
            } else {
                activeScheduleStatusFilter.add(chip.dataset.status);
            }
            const showAll = activeScheduleStatusFilter.size === 0;
            elements.scheduleStatusChips.querySelectorAll('.chip').forEach(c => {
                const active = c === allChip ? showAll : activeScheduleStatusFilter.has(c.dataset.status);
                c.classList.toggle('chip-active', active);
                c.setAttribute('aria-pressed', String(active));
            });
            fetchScheduleFromInputs();
        });
    }
    
    function switchTab(tabId) {
        // Update active nav item and aria-current
        elements.navItems.forEach(nav => {
            nav.classList.remove('active');
            nav.removeAttribute('aria-current');
        });
        // Prefer .btn-nav over the patient-ctx-pill when both share data-tab
        const activeNavItem = document.querySelector(`.btn-nav.nav-item[data-tab="${tabId}"]`)
            || document.querySelector(`.nav-item[data-tab="${tabId}"]`);
        if (activeNavItem) {
            activeNavItem.classList.add('active');
            activeNavItem.setAttribute('aria-current', 'page');
        }
        
        // Show corresponding tab content
        elements.tabContents.forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        
        const targetTab = document.getElementById(`${tabId}-tab`);
        if (targetTab) {
            targetTab.classList.add('active');
            targetTab.removeAttribute('hidden');
            targetTab.style.display = 'block';
        }

        // Reflect the tab in the URL fragment (no scroll, no history entry)
        history.replaceState(null, '', `#${tabId}`);

        if (tabId === 'schedule') {
            setPageTitle('Schedule');
        } else if (tabId === 'search' || !elements.patientName?.textContent) {
            setPageTitle(null);
        }

        if (tabId === 'schedule' && !elements.scheduleTable?.dataset.loaded && getCredentials()) {
            fetchScheduleFromInputs();
        }

        if (tabId === 'imaging') {
            loadImagingLazily();
        }

        if (tabId === 'laboratory') {
            loadLaboratoryLazily();
        }

        if (tabId === 'epicrisis') {
            loadEpicrisisLazily();
        }

        if (tabId === 'report') {
            updateAiEmptyState();
            loadReportLazily().then(updateAiEmptyState);
        }

        if (tabId === 'ai') {
            updateAiEmptyState();
            loadReportLazily().then(updateAiEmptyState);
        }
    }

    let pendingEpicrisisData = null;
    let pendingReportData = null;
    let pendingAnalysesData = null;
    let cachedServiceRequests = null;

    // Bumped on every new patient load (clearResults) so background prefetch
    // work scheduled for a previous patient becomes a no-op once stale.
    let dataGeneration = 0;
    let prefetchTimers = [];

    // ── Schedule idle-prefetch ──────────────────────────────────────────
    // Warms the ImagingStudy/DiagnosticReport cache for rows currently listed
    // in the schedule, one request at a time, only while the user is idle.
    // Any mouse/keyboard/scroll activity immediately postpones the next
    // fetch — this must never compete with an interactive request for
    // Hipocrate's attention.
    let lastActivityTs = Date.now();
    ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach(evt => {
        window.addEventListener(evt, () => { lastActivityTs = Date.now(); }, { passive: true, capture: true });
    });

    const SCHEDULE_PREFETCH_IDLE_GATE = 1500; // ms of quiet required before touching Hipocrate
    const SCHEDULE_PREFETCH_GAP = 1000;        // spacing between prefetch requests once idle
    let scheduleGeneration = 0;
    let schedulePrefetchQueue = [];
    let schedulePrefetchTimer = null;
    const scheduleFetchedIds = new Set(); // avoids re-warming rows already fetched this session

    function stopSchedulePrefetch() {
        if (schedulePrefetchTimer) { clearTimeout(schedulePrefetchTimer); schedulePrefetchTimer = null; }
        schedulePrefetchQueue = [];
    }

    function queueSchedulePrefetchStep(gen, delay) {
        schedulePrefetchTimer = setTimeout(() => schedulePrefetchStep(gen), delay);
    }

    function schedulePrefetchStep(gen) {
        schedulePrefetchTimer = null;
        if (gen !== scheduleGeneration || document.hidden) return; // schedule changed or tab backgrounded
        const idleFor = Date.now() - lastActivityTs;
        if (idleFor < SCHEDULE_PREFETCH_IDLE_GATE) {
            queueSchedulePrefetchStep(gen, SCHEDULE_PREFETCH_IDLE_GATE - idleFor);
            return;
        }
        const item = schedulePrefetchQueue.shift();
        if (!item) return; // queue drained
        if (scheduleFetchedIds.has(item.id)) {
            schedulePrefetchStep(gen); // already warm, move on without waiting
            return;
        }
        scheduleFetchedIds.add(item.id);
        const endpoint = item.isImaging ? `/api/study/${item.id}` : `/api/report/${item.id}`;
        apiFetch(endpoint).catch(() => {}).finally(() => {
            if (gen !== scheduleGeneration) return;
            queueSchedulePrefetchStep(gen, SCHEDULE_PREFETCH_GAP);
        });
    }

    // Only warm rows whose report is likely to actually exist — no point
    // hitting Hipocrate for requests that haven't reached the lab yet.
    const SCHEDULE_PREFETCH_STATUSES = new Set(['draft', 'active', 'completed', 'ended']);
    const SCHEDULE_PREFETCH_IMAGING = new Set(['radio', 'ct', 'irm', 'eco', 'rads', 'fluoro']);

    function startSchedulePrefetch(entries) {
        scheduleGeneration++;
        stopSchedulePrefetch();
        const gen = scheduleGeneration;
        schedulePrefetchQueue = entries
            .filter(r => SCHEDULE_PREFETCH_STATUSES.has(r.status_code) && !scheduleFetchedIds.has(r.request_id))
            .map(r => ({ id: r.request_id, isImaging: SCHEDULE_PREFETCH_IMAGING.has(r.modality || '') }));
        if (schedulePrefetchQueue.length) queueSchedulePrefetchStep(gen, SCHEDULE_PREFETCH_IDLE_GATE);
    }

    async function fetchRequestList() {
        if (cachedServiceRequests !== null) return cachedServiceRequests;
        const result = await fetchAnalysesData(pendingAnalysesData.patientCode);
        cachedServiceRequests = result;
        return result;
    }

    // Quietly warm Imaging / Laboratory / Epicrisis data in the background
    // after a patient loads, so the first tab click is instant. Delayed and
    // staggered so it doesn't compete with the initial render or fire a
    // burst of simultaneous requests; fully silent (no loading UI) — on
    // failure the user just gets a normal fetch when they click the tab.
    function schedulePrefetch(patientCode, patientData) {
        const myGeneration = dataGeneration;
        const BASE_DELAY = 2500;    // let the patient tab render/settle first
        const JITTER_SPREAD = 4000; // spread targets over this window, no burst
        const targets = [
            () => prefetchImaging(patientCode, myGeneration),
            () => prefetchLaboratory(patientData, myGeneration),
            () => prefetchEpicrisis(patientData, myGeneration),
        ];
        targets.forEach((task, i) => {
            const delay = BASE_DELAY
                + (i * JITTER_SPREAD / targets.length)
                + Math.random() * (JITTER_SPREAD / targets.length);
            prefetchTimers.push(setTimeout(() => {
                if (myGeneration !== dataGeneration) return;
                task();
            }, delay));
        });
    }

    async function prefetchImaging(patientCode, gen) {
        if (gen !== dataGeneration) return;
        try {
            const result = await fetchRequestList(); // memoized; also warms Laboratory
            if (gen !== dataGeneration) return;
            if (pendingReportData) {
                pendingReportData.analysesData = result.data || { requests: [] };
            }
        } catch (err) {
            log('Prefetch imaging failed (silent):', err);
        }
    }

    async function prefetchLaboratory(patientData, gen) {
        if (gen !== dataGeneration) return;
        try {
            await fetchRequestList(); // shares cachedServiceRequests with imaging
            if (gen !== dataGeneration) return;
            const sd = new Date(); sd.setDate(sd.getDate() - 90);
            await apiFetch(`/api/observation?patient=${encodeURIComponent(patientData.id)}&start_date=${localDateStr(sd)}`);
        } catch (err) {
            log('Prefetch laboratory failed (silent):', err);
        }
    }

    async function prefetchEpicrisis(patientData, gen) {
        if (gen !== dataGeneration) return;
        try {
            const checkoutIds = extractCheckoutIds(patientData);
            const checkinIds = extractCheckinIds(patientData);
            if (!checkoutIds.length && !checkinIds.length) return;
            await Promise.all([
                limitedMap(checkoutIds, MAX_CONCURRENT_REQUESTS, async id => {
                    if (gen !== dataGeneration) return null;
                    try { return await fetchEncounterDataForCheckout(id); }
                    catch { return null; }
                }),
                // Also warms the checkin side of computeCurrentEpisodeBoundary's
                // cache.encounters lookups, not just the Epicrisis tab.
                limitedMap(checkinIds, MAX_CONCURRENT_REQUESTS, async id => {
                    if (gen !== dataGeneration) return null;
                    try { return await fetchEncounterDataForCheckin(id); }
                    catch { return null; }
                }),
            ]);
        } catch (err) {
            log('Prefetch epicrisis failed (silent):', err);
        }
    }

    async function loadImagingLazily() {
        if (!pendingAnalysesData || elements.imagingGrid?.dataset.loaded) return;
        elements.imagingGrid.dataset.loaded = '1';
        const { patientData } = pendingAnalysesData;
        const patientLabel = formatPatientName(patientData);
        showLoading(`Loading imaging studies for ${patientLabel}…`);
        try {
            setLoadingStep('Querying Hipocrate for imaging requests…');
            const result = await fetchRequestList();
            const bundle = result.data || { requests: [] };
            const IMAGING = ['radio', 'ct', 'irm', 'eco', 'rads'];
            const entries = (bundle.requests || []).filter(e => IMAGING.includes(e.type));
            const allDates = (bundle.requests || []).map(e => e.date_time).filter(Boolean);
            setLoadingStep(entries.length ? `Organising ${entries.length} imaging studies…` : 'No imaging studies found.');
            await populateStudyGrid(entries, {
                grid: elements.imagingGrid, noData: elements.imagingNoData,
                eyebrow: elements.imagingEyebrow, eyebrowLabel: `Imaging · ${patientLabel}`,
                metaId: 'imagingMeta', types: IMAGING, patientData, allDates,
            });
            if (pendingReportData) pendingReportData.analysesData = bundle;
            hideLoading();
        } catch (err) {
            delete elements.imagingGrid.dataset.loaded;
            console.error('Error loading imaging:', err);
            hideLoading();
        }
    }

    async function loadLaboratoryLazily() {
        if (!pendingAnalysesData || elements.labGrid?.dataset.loaded) return;
        elements.labGrid.dataset.loaded = '1';
        const { patientData } = pendingAnalysesData;
        const patientLabel = formatPatientName(patientData);
        showLoading(`Loading lab results for ${patientLabel}…`);
        try {
            setLoadingStep('Querying Hipocrate for lab requests…');
            const result = await fetchRequestList();
            const bundle = result.data || { requests: [] };
            const LAB = ['lab'];
            const entries = (bundle.requests || []).filter(e => LAB.includes(e.type));
            const allDates = (bundle.requests || []).map(e => e.date_time).filter(Boolean);
            setLoadingStep(entries.length ? `Organising ${entries.length} lab results…` : 'No lab results found.');
            await populateStudyGrid(entries, {
                grid: elements.labGrid, noData: elements.labNoData,
                eyebrow: elements.labEyebrow, eyebrowLabel: `Laboratory · ${patientLabel}`,
                metaId: 'labMeta', types: LAB, patientData, allDates,
            });
            loadTrends(patientData.id);
            hideLoading();
        } catch (err) {
            delete elements.labGrid.dataset.loaded;
            console.error('Error loading lab results:', err);
            hideLoading();
        }
    }

    async function loadReportLazily() {
        if (!pendingReportData || elements.patientReportMarkdown?.dataset.loaded) return;
        elements.patientReportMarkdown.dataset.loaded = '1';
        const name = pendingReportData.patientData?.name || 'patient';
        showLoading(`Assembling clinical report for ${name}…`);
        try {
            setLoadingStep('Compiling diagnoses, admissions and imaging history…');
            // pendingReportData.analysesData starts as an empty stub and is
            // normally backfilled by the background schedulePrefetch imaging
            // fetch — but landing here (Report/AI tab) before that prefetch
            // finishes would otherwise build the clinical text, and its AI
            // cache key, from zero imaging entries. fetchRequestList is
            // memoized, so this is a no-op once the prefetch has already run.
            if (pendingAnalysesData) {
                const result = await fetchRequestList();
                pendingReportData.analysesData = result.data || { requests: [] };
            }
            await loadAndDisplayReport(pendingReportData.patientData, pendingReportData.analysesData);
            hideLoading();
        } catch (err) {
            console.error('Error loading report:', err);
            delete elements.patientReportMarkdown.dataset.loaded;
            showOverlayError('Failed to assemble patient report');
        }
    }

    async function loadEpicrisisLazily() {
        if (!pendingEpicrisisData || elements.epicrisisContent?.dataset.loaded) return;
        elements.epicrisisContent.dataset.loaded = '1';
        const name = pendingEpicrisisData?.name || 'patient';
        showLoading(`Loading hospitalization records for ${name}…`);
        try {
            setLoadingStep('Fetching hospitalization episodes from Hipocrate…');
            await loadAndDisplayEpicrisis(pendingEpicrisisData);
            hideLoading();
        } catch (err) {
            console.error('Error loading epicrisis:', err);
            delete elements.epicrisisContent.dataset.loaded;
            showOverlayError('Failed to load hospitalization records');
        }
    }
    
    async function handleFormSubmit(e) {
        e.preventDefault();
        
        const cnp = elements.cnpInput.value.trim();
        log('Form submitted with CNP:', cnp);
        
        // Enhanced input validation
        if (!cnp) {
            showError('Please enter a valid patient identifier (CNP, partial CNP, patient code, or patient name)');
            return;
        }
        
        // Enhanced validation with better error messages
        const validation = validatePatientIdentifier(cnp);
        if (!validation.isValid) {
            showError(validation.message);
            return;
        }
        
        // Clear previous results and show loading state
        clearResults();
        const searchTitles = {
            cnp:         'Looking up patient by CNP…',
            partial_cnp: 'Searching by partial CNP…',
            code:        'Looking up patient by ID…',
            name:        `Searching by name "${cnp}"…`,
        };
        showLoading(searchTitles[validation.type] || 'Searching for patient…');
        hideError();

        try {
            const searchSteps = {
                cnp:         `Querying Hipocrate for CNP ${cnp}…`,
                partial_cnp: `Querying Hipocrate for partial CNP ${cnp}…`,
                code:        `Querying Hipocrate for patient ID ${cnp}…`,
                name:        `Searching patient registry for "${cnp}"…`,
            };
            setLoadingStep(searchSteps[validation.type] || 'Searching patient registry…');
            log('Starting patient search...');
            const searchResult = await performPatientSearch(cnp);
            log('Patient search result:', searchResult);

            if (!searchResult.success) {
                if (searchResult.needsSelection) {
                    hideLoading();
                    const chosen = await showPatientSelection(searchResult.candidates);
                    if (!chosen) return; // user dismissed
                    showLoading(`Loading record for ${chosen.name || chosen.id}…`);
                    setLoadingStep('Fetching full patient record from Hipocrate…');
                    const r = await apiFetch(`/api/patient/${chosen.id}`);
                    searchResult.patientData = r.ok ? patientFromApi(await r.json()) : patientFromApi({ patient: chosen });
                    searchResult.patientCode = chosen.id;
                    addToRecentSearches(cnp, searchResult.patientData);
                } else {
                    showOverlayError(searchResult.message);
                    return;
                }
            }

            const { patientData, patientCode } = searchResult;
            if (!patientCode) {
                showOverlayError('Could not determine patient ID. Please try again.');
                return;
            }
            log('Patient data retrieved:', patientData);
            log('Patient code:', patientCode);

            const patientName = patientData.name || patientCode;
            setLoadingStep(`Building profile for ${patientName}…`);
            log('Displaying patient data...');
            await displayPatientData(patientData);

            // Imaging + lab + trends are lazy-loaded on first visit to their respective tabs
            pendingAnalysesData = { patientCode, patientData };
            cachedServiceRequests = null;
            if (elements.imagingGrid) delete elements.imagingGrid.dataset.loaded;
            if (elements.labGrid) delete elements.labGrid.dataset.loaded;

            // Epicrisis is lazy-loaded on first visit to its tab
            pendingEpicrisisData = patientData;
            if (elements.epicrisisContent) delete elements.epicrisisContent.dataset.loaded;

            // Report is lazy-loaded on first visit to its tab (analysesData filled in after Analyses tab loads)
            pendingReportData = { patientData, analysesData: { requests: [] } };
            if (elements.patientReportMarkdown) delete elements.patientReportMarkdown.dataset.loaded;

            log('Switching to patient tab...');
            switchToPatientTab();
            schedulePrefetch(patientCode, patientData);

            log('All data loading complete');
            hideLoading();

        } catch (err) {
            console.error('Error in handleFormSubmit:', err);
            showOverlayError('An unexpected error occurred. Please try again.');
        }
    }

    // Force-reload the currently displayed patient's demographic, imaging,
    // lab, and Observation data from Hipocrate, bypassing the server-side
    // cache once (?refresh=1). Individual imaging/lab report detail pages
    // are left alone — those are cheap to reopen and refresh correctly on
    // their own when a report is written.
    async function refreshCurrentPatient() {
        if (!pendingAnalysesData?.patientCode) return;
        const { patientCode } = pendingAnalysesData;
        const btn = elements.refreshPatientBtn;
        const originalHTML = btn ? btn.innerHTML : null;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-sync-alt fa-spin" aria-hidden="true"></i><span>Refreshing…</span>';
        }
        try {
            const r = await apiFetch(`/api/patient/${patientCode}?refresh=1`);
            if (!r.ok) throw new Error(`Server error: ${r.status}`);
            const patientData = patientFromApi(await r.json());

            displayPatientData(patientData);

            pendingAnalysesData = { patientCode, patientData };
            cachedServiceRequests = null;
            if (elements.imagingGrid) delete elements.imagingGrid.dataset.loaded;
            if (elements.labGrid) delete elements.labGrid.dataset.loaded;

            pendingEpicrisisData = patientData;
            if (elements.epicrisisContent) delete elements.epicrisisContent.dataset.loaded;

            pendingReportData = { patientData, analysesData: { requests: [] } };
            if (elements.patientReportMarkdown) delete elements.patientReportMarkdown.dataset.loaded;

            // Re-run whichever tab is currently active so its content reloads
            // against the now-purged server-side caches.
            const activeTabId = document.querySelector('.tab-content.active')?.id?.replace('-tab', '') || 'patient';
            switchTab(activeTabId);

            dataGeneration++;
            prefetchTimers.forEach(clearTimeout);
            prefetchTimers = [];
            schedulePrefetch(patientCode, patientData);
        } catch (err) {
            console.error('Error refreshing patient:', err);
            showOverlayError('Failed to refresh patient data');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHTML;
            }
        }
    }
    
    // Enhanced validation function
    function validatePatientIdentifier(identifier) {
        const trimmed = identifier.trim();
        
        if (!trimmed) {
            return { isValid: false, message: 'Please enter a valid patient identifier.' };
        }
        
        if (/^\d{13}$/.test(trimmed)) return { isValid: true, type: 'cnp' };
        if (/^\d+\*$/.test(trimmed))  return { isValid: true, type: 'partial_cnp' };
        
        // Patient code validation (alphanumeric with common patterns)
        if (/^[A-Za-z0-9\-_]+$/.test(trimmed)) {
            return { isValid: true, type: 'code' };
        }

        // Patient name validation — Unicode letters to support Romanian diacritics (ă â î ș ț etc.)
        if (/^[\p{L}\s\-'\.]+$/u.test(trimmed)) {
            return { isValid: true, type: 'name' };
        }
        
        return { 
            isValid: false, 
            message: 'Invalid format. Please enter a valid CNP, partial CNP, patient code, or patient name.' 
        };
    }
    
    async function performPatientSearch(identifier) {
        try {
            const searchResponse = await apiFetch(`/api/patient?q=${encodeURIComponent(identifier)}`);
            
            if (!searchResponse.ok) {
                if (searchResponse.status === 401) {
                    return {
                        success: false,
                        message: 'Authentication required. Please sign in again.'
                    };
                }
                if (searchResponse.status === 404) {
                    return {
                        success: false,
                        message: 'No patient found with this identifier.'
                    };
                }
                return {
                    success: false,
                    message: `Server error: ${searchResponse.status}`
                };
            }
            
            const searchData = await searchResponse.json();
            
            let patientCode = null;
            let patientData = null;
            
            if (searchData.patient) {
                // Single match: the full record (with its encounter id lists)
                patientData = patientFromApi(searchData);
                patientCode = patientData.id;
            } else if (searchData.patients && searchData.patients.length > 0) {
                if (searchData.patients.length === 1) {
                    patientCode = searchData.patients[0].id;
                    const r = await apiFetch(`/api/patient/${patientCode}`);
                    patientData = r.ok ? patientFromApi(await r.json()) : patientFromApi({ patient: searchData.patients[0] });
                } else {
                    // Multiple matches — let the user choose
                    return {
                        success: false,
                        needsSelection: true,
                        candidates: searchData.patients
                    };
                }
            } else {
                return { success: false, message: 'No patient data found.' };
            }
            
            if (!patientCode || !patientData) {
                return {
                    success: false,
                    message: 'Failed to retrieve patient data.'
                };
            }
            
            
            // Add to recent searches with patient data
            addToRecentSearches(identifier, patientData);
            
            return {
                success: true,
                patientData,
                patientCode,
                message: 'Patient search completed successfully.'
            };
            
        } catch (err) {
            console.error('Error in patient search:', err);
            return {
                success: false,
                message: 'Network error. Please check your connection and try again.'
            };
        }
    }
    
    // Enhanced analyses fetching function
    function showPatientSelection(candidates) {
        return new Promise(resolve => {
            const dlg = document.createElement('dialog');
            dlg.className = 'patient-select-dialog';
            dlg.setAttribute('aria-label', 'Select patient');

            const heading = document.createElement('h3');
            heading.textContent = `${candidates.length} patients found — select one:`;
            dlg.appendChild(heading);

            const dismiss = (result) => { dlg.close(); dlg.remove(); resolve(result); };

            candidates.forEach(patient => {
                const name = patient.name || patient.id;
                const cnp = patient.cnp || null;
                const dob = formatBirthDate(patient.birth_date);
                const sex = patient.sex || patient.gender;
                const gender = sex ? (sex === 'male' ? 'M' : 'F') : null;
                const meta = [cnp, dob, gender].filter(Boolean).join(' · ');
                const btn = document.createElement('button');
                btn.className = 'btn-secondary';
                btn.title = 'Select this patient';
                btn.style.cssText = 'display:block;width:100%;margin-top:var(--space-8);text-align:left';
                const nameEl = document.createElement('span');
                nameEl.style.cssText = 'display:block;font-weight:var(--font-weight-semibold)';
                nameEl.textContent = name;
                btn.appendChild(nameEl);
                if (meta) {
                    const metaEl = document.createElement('span');
                    metaEl.style.cssText = 'display:block;font-size:var(--font-size-xs);color:var(--muted);margin-top:2px';
                    metaEl.textContent = meta;
                    btn.appendChild(metaEl);
                }
                btn.addEventListener('click', () => dismiss(patient));
                dlg.appendChild(btn);
            });

            const cancel = document.createElement('button');
            cancel.className = 'btn-secondary';
            cancel.title = 'Cancel selection';
            cancel.style.cssText = 'display:block;width:100%;margin-top:var(--space-16)';
            cancel.textContent = 'Cancel';
            cancel.addEventListener('click', () => dismiss(null));
            dlg.appendChild(cancel);

            // Native <dialog> handles Escape automatically via the cancel event
            dlg.addEventListener('cancel', (e) => { e.preventDefault(); dismiss(null); });

            document.body.appendChild(dlg);
            dlg.showModal();
            // Focus first button after paint
            requestAnimationFrame(() => dlg.querySelector('button')?.focus());
        });
    }

    async function fetchAnalysesData(patientCode) {
        try {
            
            const analysesResponse = await apiFetch(`/api/request?patient=${patientCode}`);
            
            if (!analysesResponse.ok) {
                if (analysesResponse.status === 401) {
                    return {
                        success: false,
                        message: 'Authentication required. Please sign in again.'
                    };
                }
                if (analysesResponse.status === 404) {
                    return {
                        success: true, // Not an error, just no data
                        data: { requests: [] },
                        message: 'No diagnostic reports found for this patient.'
                    };
                }
                return {
                    success: false,
                    message: `Error loading diagnostic reports: ${analysesResponse.status}`
                };
            }
            
            const analysesData = await analysesResponse.json();
            
            return {
                success: true,
                data: analysesData,
                message: 'Diagnostic reports loaded successfully.'
            };
            
        } catch (err) {
            console.error('Error fetching analyses:', err);
            return {
                success: false,
                message: 'Failed to load diagnostic reports. Please try again.'
            };
        }
    }
    
    function switchToPatientTab() {
        // Unhide the patient nav group hidden by clearResults
        if (elements.navPatientGroup) elements.navPatientGroup.hidden = false;
        // Unhide sibling tab content panels (clearResults set hidden=true)
        ['imaging-tab', 'laboratory-tab', 'epicrisis-tab', 'report-tab'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.hidden = false;
        });
        switchTab('patient');
    }
    
    function hideLoading() {
        elements.loadingOverlay.style.display = 'none';
        if (elements.loadingSpinner) elements.loadingSpinner.hidden = false;
        if (elements.loadingError) elements.loadingError.hidden = true;
        elements.analyzeBtn.disabled = false;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }

    function showOverlayError(message) {
        if (elements.loadingSpinner) elements.loadingSpinner.hidden = true;
        if (elements.loadingErrorMsg) elements.loadingErrorMsg.textContent = message;
        if (elements.loadingError) elements.loadingError.hidden = false;
        elements.loadingOverlay.style.display = 'flex';
        elements.analyzeBtn.disabled = false;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }
    
    function clearResults() {
        dataGeneration++;
        prefetchTimers.forEach(clearTimeout);
        prefetchTimers = [];
        setPageTitle(null);
        // Clear patient data with null checks
        if (elements.patientId) elements.patientId.innerHTML = '';
        if (elements.patientName) elements.patientName.textContent = '';
        if (elements.patientNameInfo) elements.patientNameInfo.textContent = '';
        if (elements.patientAgeInfo) elements.patientAgeInfo.textContent = '';
        if (elements.patientCnp) elements.patientCnp.textContent = '';
        if (elements.patientGender) elements.patientGender.innerHTML = '';
        if (elements.patientDiagnosis) { elements.patientDiagnosis.textContent = ''; elements.patientDiagnosis.hidden = true; }
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = '';
        if (elements.patientPhone) elements.patientPhone.textContent = '';
        if (elements.patientEmail) elements.patientEmail.textContent = '';
        if (elements.patientAddress) elements.patientAddress.textContent = '';
        if (elements.navPatientLabel) elements.navPatientLabel.textContent = 'Patient Profile';
        if (elements.historyList) elements.historyList.innerHTML = '';
        if (elements.historyEmpty) elements.historyEmpty.hidden = true;
        if (elements.presentationsCount) elements.presentationsCount.textContent = '0';
        if (elements.checkinsCount) elements.checkinsCount.textContent = '0';
        if (elements.checkoutsCount) elements.checkoutsCount.textContent = '0';
        
        // Clear imaging tab
        if (elements.imagingGrid) elements.imagingGrid.innerHTML = '';
        if (elements.imagingNoData) elements.imagingNoData.style.display = 'none';
        if (elements.imagingEyebrow) elements.imagingEyebrow.textContent = 'Imaging';
        document.getElementById('imagingMeta')?.replaceChildren();
        document.querySelectorAll('#imagingChips .chip').forEach(c => {
            c.classList.toggle('chip-active', c.dataset.filter === 'all');
            c.textContent = c.textContent.replace(/\s*\(\d+\)$/, '');
            c.style.opacity = '';
            c.disabled = false;
        });
        if (elements.imagingCount) elements.imagingCount.textContent = '?';

        // Clear laboratory tab
        if (elements.labGrid) elements.labGrid.innerHTML = '';
        if (elements.labNoData) elements.labNoData.style.display = 'none';
        if (elements.labEyebrow) elements.labEyebrow.textContent = 'Laboratory';
        document.getElementById('labMeta')?.replaceChildren();
        // Remove dynamically-added section chips, keep only "All"
        document.querySelectorAll('#labChips .chip:not([data-filter="all"])').forEach(c => c.remove());
        document.querySelector('#labChips .chip[data-filter="all"]')?.classList.add('chip-active');
        if (elements.labCount) elements.labCount.textContent = '?';
        if (elements.trendsSection) elements.trendsSection.hidden = true;
        if (elements.trendsContainer) {
            elements.trendsContainer.innerHTML = '';
            delete elements.trendsContainer.dataset.markdown;
        }
        if (elements.copyLabBtn) elements.copyLabBtn.hidden = true;

        // Clear lazy-load state
        pendingAnalysesData = null;
        cachedServiceRequests = null;
        episodeBoundaryPromise = null;
        if (elements.imagingGrid) delete elements.imagingGrid.dataset.loaded;
        if (elements.labGrid) delete elements.labGrid.dataset.loaded;

        // Clear epicrisis
        pendingEpicrisisData = null;
        if (elements.epicrisisContent) {
            elements.epicrisisContent.innerHTML = '';
            delete elements.epicrisisContent.dataset.markdown;
            delete elements.epicrisisContent.dataset.loaded;
        }
        if (elements.epicrisisNoData) elements.epicrisisNoData.style.display = 'none';
        if (elements.copyEpicrisisBtn) elements.copyEpicrisisBtn.hidden = false;
        // Clear report tab
        pendingReportData = null;
        if (elements.patientReportMarkdown) {
            elements.patientReportMarkdown.innerHTML = '';
            delete elements.patientReportMarkdown.dataset.markdown;
            delete elements.patientReportMarkdown.dataset.loaded;
        }
        if (elements.patientReportBlocks) {
            delete elements.patientReportBlocks.dataset.blocks;
            // getPatientClinicalText() reads this first — left stale, it makes
            // the AI tab briefly (or indefinitely, if the tab is opened before
            // loadReportLazily() finishes) see the *previous* patient's text
            // as "content available" and auto-probe the cache under their
            // hash, redisplaying their AI card as if it belonged here.
            delete elements.patientReportBlocks.dataset.clinicalMarkdown;
        }
        const reportCard = elements.reportCard;
        if (reportCard) reportCard.hidden = true;

        // Clear AI extraction tab
        resetAiTab();

        // Hide the patient nav group (keep always-visible tabs)
        if (elements.navPatientGroup) elements.navPatientGroup.hidden = true;

        // Clear any existing toasts
        const toastContainer = document.getElementById('toast-container');
        if (toastContainer) {
            toastContainer.innerHTML = '';
        }
    }
    
    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'auto';
        const cycle = { auto: 'light', light: 'dark', dark: 'auto' };
        const newTheme = cycle[currentTheme] || 'auto';

        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);

        const themeIcon = elements.themeToggle?.querySelector('i');
        if (themeIcon) themeIcon.className = newTheme === 'dark' ? 'fas fa-sun' : newTheme === 'light' ? 'fas fa-moon' : 'fas fa-circle-half-stroke';

        // Re-render QR codes with the new theme colours
        [elements.qrLastName, elements.qrFirstName, elements.qrCnp, elements.qrBirthDate].forEach(c => {
            if (c?.dataset.qrText) renderQr(c, c.dataset.qrText);
        });
    }

    let whoamiData = null;
    let hipocrateUrl = localStorage.getItem('hipocrateUrl') || null;
    let canWriteReports = false;
    let whoamiInFlight = null;

    // Single-flight: many callers (initApp, every analysis card's
    // fetchAndFillReport retry, the account modal, …) can call this within
    // the same tick — e.g. once per card right after a page reload, while
    // whoamiData is still unset. Without de-duping, each one fired its own
    // /api/whoami request instead of sharing the one already in progress.
    function formatUserDisplayName(user) {
        return user.display_name
            ? user.display_name.toLowerCase()
            : (user.username || '').replace(/\./g, ' ');
    }

    async function fetchWhoami() {
        if (whoamiData) return whoamiData;
        if (whoamiInFlight) return whoamiInFlight;
        whoamiInFlight = (async () => {
            try {
                const resp = await apiFetch('/api/whoami');
                const data = await resp.json().catch(() => ({}));
                // Extract these fields regardless of HTTP status — server always sets them
                if (data.hipocrate_url) {
                    hipocrateUrl = data.hipocrate_url.replace(/\/$/, '');
                    localStorage.setItem('hipocrateUrl', hipocrateUrl);
                }
                canWriteReports = data.can_write_reports === true;
                if (!resp.ok || data.status !== 'success' || !data.user) {
                    throw new Error(data.message || `Whoami failed (${resp.status})`);
                }
                whoamiData = data.user;
                if (elements.userButton) {
                    const label = formatUserDisplayName(whoamiData);
                    if (label) elements.userButton.title = label;
                }
                return whoamiData;
            } finally {
                whoamiInFlight = null;
            }
        })();
        return whoamiInFlight;
    }

    async function showUserModal() {
        const tmpl = document.getElementById('user-modal-template');
        const modal = tmpl.content.cloneNode(true).querySelector('dialog');

        const nameEl = modal.querySelector('.user-modal-name');
        nameEl.textContent = 'Loading…';

        const closeModal = () => { modal.close(); modal.remove(); };
        modal.querySelectorAll('[data-close-modal], .close').forEach(btn => {
            btn.addEventListener('click', closeModal);
        });
        modal.addEventListener('cancel', () => modal.remove());

        modal.querySelector('.btn-user-logout').addEventListener('click', async () => {
            try {
                const resp = await apiFetch('/api/logout', { method: 'POST' });
                if (!resp.ok) throw new Error(`Logout failed (${resp.status})`);
                whoamiData = null;
                clearCredentials();
                closeModal();
                showToast('Signed out.', 'success');
                showLoginDialog();
            } catch (err) {
                showToast(`Logout failed: ${err.message}`, 'error');
            }
        });

        document.body.appendChild(modal);
        modal.showModal();

        try {
            const user = await fetchWhoami();
            const displayName = formatUserDisplayName(user);
            nameEl.textContent = displayName || 'Unknown user';
            modal.querySelector('.user-detail-username').textContent = user.username || '—';
            modal.querySelector('.user-detail-id').textContent = user.id || '—';
            modal.querySelector('.user-detail-reports').textContent = canWriteReports ? 'Can write reports' : '—';
        } catch (err) {
            nameEl.textContent = 'Unavailable';
            showToast(`Could not load user info: ${err.message}`, 'error');
        }
    }

    
    // Chips filter across both episode sections; hide a section's divider
    // header once every card under it is filtered out, so no empty
    // "Current Episode" / "Prior Episodes" heading is left dangling.
    function updateEpisodeDividers(gridEl) {
        if (!gridEl) return;
        let visibleSinceDivider = 0;
        let lastDivider = null;
        for (const child of gridEl.children) {
            if (child.classList.contains('episode-divider')) {
                if (lastDivider) lastDivider.style.display = visibleSinceDivider > 0 ? '' : 'none';
                lastDivider = child;
                visibleSinceDivider = 0;
            } else if (child.classList.contains('analysis-card') && child.style.display !== 'none') {
                visibleSinceDivider++;
            }
        }
        if (lastDivider) lastDivider.style.display = visibleSinceDivider > 0 ? '' : 'none';
    }

    function filterGrid(gridEl, noDataEl, filterType = 'all') {
        if (!gridEl) return;
        const cards = gridEl.querySelectorAll('.analysis-card');
        let visible = 0;
        cards.forEach(card => {
            const show = filterType === 'all' || card.dataset.type === filterType;
            card.style.display = show ? 'block' : 'none';
            if (show) visible++;
        });
        updateEpisodeDividers(gridEl);
        if (noDataEl) noDataEl.style.display = visible === 0 ? 'block' : 'none';
    }

    function filterLabGrid(section = 'all') {
        if (elements.labGrid) {
            let visible = 0;
            elements.labGrid.querySelectorAll('.analysis-card').forEach(card => {
                const secs = card.dataset.labSection ? card.dataset.labSection.split('\t') : [];
                const show = section === 'all' || secs.includes(section);
                card.style.display = show ? 'block' : 'none';
                if (show) visible++;
            });
            updateEpisodeDividers(elements.labGrid);
            if (elements.labNoData) elements.labNoData.style.display = visible === 0 ? 'block' : 'none';
        }
        elements.trendsContainer?.querySelectorAll('[data-trend-section]').forEach(wrap => {
            wrap.style.display = (section === 'all' || wrap.dataset.trendSection === section) ? '' : 'none';
        });
    }

    function addLabChips(sections) {
        const container = document.getElementById('labChips');
        if (!container) return;
        for (const sec of sections) {
            if (!sec || container.querySelector(`[data-filter="${CSS.escape(sec)}"]`)) continue;
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'chip';
            chip.dataset.filter = sec;
            chip.textContent = sec.split(' ').map(w => w.charAt(0) + w.slice(1).toLowerCase()).join(' ');
            chip.title = `Filter: ${chip.textContent}`;
            container.appendChild(chip);
        }
    }
    
    async function copyTextToClipboard(text) {
        if (!text || text === '—') {
            showToast('No content to copy', 'warning');
            return;
        }
        const done = () => showToast('Copied to clipboard', 'success');
        if (navigator.clipboard?.writeText) {
            try { await navigator.clipboard.writeText(text); done(); return; }
            catch (_) { /* fall through */ }
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.focus(); ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        ok ? done() : showToast('Failed to copy to clipboard', 'error');
    }

    // YYMMDD from an ISO date/datetime string, parsed as plain text (no
    // Date object) to avoid the UTC-lag issue on date-only values.
    function formatIdDate(iso) {
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
        return m ? m[1].slice(2) + m[2] + m[3] : '';
    }

    // Lowercase, hyphen-joined, diacritics stripped (e.g. "Ștefan" → "stefan")
    // — one slug segment per space-separated word.
    function slugifyNamePart(s) {
        return (s || '')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim()
            .split(/\s+/)
            .filter(Boolean)
            .join('-');
    }

    // DokuLLM ID stub: YYMMDD-family-given... — examDateIso is the exam's
    // own date (the request's date_time), not today's date.
    function buildExamIdStub(patientData, examDateIso) {
        const dateStr = formatIdDate(examDateIso);
        const family = slugifyNamePart(patientData?.family_name);
        const given = slugifyNamePart(patientData?.given_name);
        return [dateStr, family, given].filter(Boolean).join('-');
    }

    // "Full Name | Sex | Age | indication | CT Cerebral nativ" stub for an
    // imaging card — indication left blank (not omitted) if absent.
    function buildExamStub(article) {
        const patientData = pendingAnalysesData?.patientData;
        const fullName = formatPatientName(patientData);
        const sex = formatGender(patientData?.sex);
        const ageRaw = calculateAge(patientData?.birth_date);
        const age = ageRaw !== 'N/A' ? ageRaw : '';
        const indication = article.querySelector('.card-indication-text')?.textContent
            ?.replace(/^\s*·\s*/, '').trim() || '';
        const examType = article.querySelector('.type-text')?.textContent || '';
        const region = article.querySelector('.card-regions')?.textContent
            ?.replace(/^\s*·\s*/, '').trim() || '';
        const exam = [examType, region].filter(Boolean).join(' ');
        return [fullName, sex, age, indication, exam].join(' | ');
    }

    async function copyMarkdown(markdownEl, btn, flashFn) {
        const markdown = markdownEl?.dataset.markdown;
        if (!markdown) {
            showToast('No content to copy', 'warning');
            return;
        }
        const flash = flashFn || (() => {
            const orig = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> <span>Copied!</span>';
            setTimeout(() => { btn.innerHTML = orig; }, 2000);
        });
        if (navigator.clipboard?.writeText) {
            try { await navigator.clipboard.writeText(markdown); flash(); return; }
            catch (_) { /* fall through */ }
        }
        const ta = document.createElement('textarea');
        ta.value = markdown;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.focus(); ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        ok ? flash() : showToast('Failed to copy to clipboard', 'error');
    }

    // Icon-only flash for compact copy buttons: swap the glyph to a check
    // briefly, no text, so the button doesn't change width.
    function flashIcon(btn) {
        const icon = btn.querySelector('i');
        if (!icon) return;
        const orig = icon.className;
        icon.className = 'fas fa-check';
        setTimeout(() => { icon.className = orig; }, 1500);
    }

    function copyEpicrisisMarkdown() { return copyMarkdown(elements.epicrisisContent, elements.copyEpicrisisBtn, () => flashIcon(elements.copyEpicrisisBtn)); }
    function copyReportMarkdown()    { return copyMarkdown(elements.patientReportMarkdown, elements.copyReportBtn, () => flashIcon(elements.copyReportBtn)); }
    function copyLabMarkdown()       { return copyMarkdown(elements.trendsContainer, elements.copyLabBtn, () => flashIcon(elements.copyLabBtn)); }

    // ── AI summaries ──────────────────────────────────────────────────
    // Free-text AI aids wired into each tab as a per-item "AI" button. All
    // go through one endpoint (POST /api/ai/summarize {kind, text}); the
    // server picks the model tier and prompt per kind (see llm/prompts.py).
    // Deliberately unverified — every card carries the amber "verify against
    // source" badge and is never conflated with scraped/validated data.

    // Serialized lab-trend text for the Lab Trends AI button (pathological
    // rows only), rebuilt each time renderTrends() runs; labHasAbnormal is
    // false when every value is within range.
    let labAiText = '';
    let labHasAbnormal = false;

    // Renal-function extract for the contrast_safety AI prompt
    // (llm/prompts/contrast_safety.md), rebuilt alongside labAiText in
    // renderTrends() — but unconditional on abnormality, unlike labAiText:
    // a normal creatinine/eGFR is exactly what that check wants to see, not
    // something to hide because nothing is flagged H/L. No button wired to
    // this yet — see buildContrastSafetyText() below.
    let renalLabAiText = '';

    // Analyte names counted as "renal function" — matched case-insensitively
    // against the Hipocrate-supplied analyte name text. There's no
    // controlled vocabulary to key off (analyte names come straight through
    // from obs.code?.text in renderTrends), so this is a substring match
    // over the Romanian/English terms actually seen in lab panels: creatinine
    // and estimated/measured glomerular filtration rate.
    const RENAL_ANALYTE_RE = /creatinin|e-?gfr|\brfg\b|filtrare glomerular|clearance.*creatin/i;

    // Keywords marking a sentence as contrast-relevant (allergy/reaction to
    // contrast media, or the other flags contrast_safety.md checks for).
    // The clinical record can be long (years of history); rather than send
    // all of it, buildContrastSafetyText() below keeps only sentences
    // matching this so the LLM call stays small and on-topic.
    const CONTRAST_FLAG_RE = /alergi|reac[țt]i|\biod\b|iodat|contrast|iomeron|ultravist|omnipaque|visipaque|optiray|xenetix|gadolini|gadovist|dotarem|magnevist|primovist|\bastm|metformin|mielom multiplu|paraproteinemi/i;

    // Splits clinical markdown into sentences (line-based, then split on
    // sentence-ending punctuation within each line so list items without a
    // period still count as one sentence) and keeps only the ones matching
    // CONTRAST_FLAG_RE, so passages stay whole and meaningful rather than
    // being cut mid-sentence.
    function extractContrastRelevantText(text) {
        if (!text) return '';
        const kept = [];
        for (const line of text.split(/\n+/)) {
            const trimmedLine = line.trim();
            if (!trimmedLine) continue;
            const sentences = trimmedLine.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [trimmedLine];
            for (const raw of sentences) {
                const sentence = raw.trim();
                if (sentence && CONTRAST_FLAG_RE.test(sentence)) kept.push(sentence);
            }
        }
        return kept.join(' ');
    }

    function resetAiTab() {
        if (elements.aiEmptyState) elements.aiEmptyState.hidden = false;
        if (elements.aiReportBtn) elements.aiReportBtn.hidden = true;
        for (const btn of elements.aiPreExamBtns || []) btn.hidden = true;
        if (elements.aiLabBtn) elements.aiLabBtn.hidden = true;
        if (elements.contrastSafetyBtn) elements.contrastSafetyBtn.hidden = true;
        // Drop any rendered AI cards from a previous patient. querySelectorAll
        // does not descend into <template> content, so the template card is safe.
        document.querySelectorAll('.ai-summary-card').forEach(card => card.remove());
        for (const btn of [elements.aiReportBtn, ...(elements.aiPreExamBtns || []), elements.aiLabBtn, elements.contrastSafetyBtn, elements.patientAiSummaryBtn]) {
            if (btn) btn._aiCard = null;
        }
        labAiText = '';
        labHasAbnormal = false;
        renalLabAiText = '';
    }

    // Clinical text used by the Report and Pre-Exam summaries — carries only
    // the patientContextHeader() line (initials/age/sex/diagnosis, never
    // name/DOB/CNP) plus admission/lab/imaging content; excludes the
    // deterministic patient identity block rendered on the Report tab
    // itself. Falls back to the full markdown if the clinical-only stash
    // isn't populated (e.g. an older cached load).
    function getPatientClinicalText() {
        const clinical = elements.patientReportBlocks?.dataset.clinicalMarkdown;
        if (clinical && clinical.trim()) return clinical;
        return elements.patientReportMarkdown?.dataset.markdown || null;
    }

    // Assembles the 'contrast_safety' AI prompt's two-section input (see
    // llm/prompts/contrast_safety.md): the renal-analyte extract built in
    // renderTrends() (renalLabAiText — empty until the Lab Trends tab has
    // loaded for this patient) plus the same clinical record text the
    // report/pre-exam prompts use. No button wired to this yet.
    function buildContrastSafetyText() {
        const fullClinical = getPatientClinicalText();
        if (!renalLabAiText && !fullClinical) return '';
        const patientData = pendingAnalysesData?.patientData;
        const header = patientContextHeader(patientData);
        const renalSection = `### Renal function\n${renalLabAiText || 'No renal function analytes on file.'}`;
        const relevantClinical = extractContrastRelevantText(fullClinical);
        const clinicalText = relevantClinical
            || (fullClinical ? 'No contrast-relevant mentions found in clinical record.' : 'No clinical record available.');
        const clinicalSection = `### Clinical record\n${clinicalText}`;
        return header + renalSection + '\n\n' + clinicalSection;
    }

    // Toggle the availability of the singleton AI buttons when patient
    // clinical text becomes (un)available.
    function updateAiEmptyState() {
        const hasContent = !!getPatientClinicalText();
        if (elements.aiEmptyState) elements.aiEmptyState.hidden = hasContent;
        if (elements.aiReportBtn) elements.aiReportBtn.hidden = !hasContent;
        for (const btn of elements.aiPreExamBtns || []) btn.hidden = !hasContent;
        if (hasContent) {
            // Silently redisplay a previously generated summary for this patient, if any.
            runAiSummary(elements.aiReportBtn, 'report',
                () => elements.reportCard, getPatientClinicalText, { auto: true });
            for (const btn of elements.aiPreExamBtns || []) {
                runAiSummary(btn, btn.dataset.kind,
                    () => elements.aiPreExamAnchor, getPatientClinicalText, { auto: true });
            }
            // Silently redisplay a previously generated one-liner for this
            // patient, if any — same 'pre_exam_oneliner' kind/cache as the
            // pre-exam toolbar buttons, but rendered inline in the profile card.
            runAiSummary(elements.patientAiSummaryBtn, 'pre_exam_oneliner',
                () => null, getPatientClinicalText,
                { auto: true, inline: true, intoAnchorParent: () => elements.patientAiSummaryAnchor });
        }
    }

    // Shows a "Preparing data…" placeholder on an AI singleton button while
    // an async prep step (e.g. loadReportLazily) runs, so a click isn't
    // silent until it resolves — used by AI actions whose getText() depends
    // on data that isn't guaranteed to be loaded yet. Returns the card (or
    // undefined if `button` is falsy); the caller awaits its own prep step,
    // then removes the card and re-enables the button if the data still
    // isn't there (runAiSummary's own empty-text toast covers that case,
    // but only once the placeholder/disabled state are cleared first).
    function showAiPreparingPlaceholder(button, anchor, intoParent, kind) {
        if (!button) return;
        let card = button._aiCard;
        if (!card || !card.isConnected) {
            card = makeAiCard(true);
            wireAiCardCopy(card);
            button._aiCard = card;
        }
        setAiCardBadgeTitle(card, kind);
        placeAiCard(card, anchor, intoParent);
        const body = card.querySelector('.ai-summary-body');
        card.classList.remove('ai-card-error');
        body.classList.add('ai-summary-loading');
        body.textContent = 'Preparing data…';
        button.disabled = true;
        return card;
    }

    // Profile tab's "AI Summary" Generate button. Unlike aiReportBtn (only
    // shown once loadReportLazily has already assembled the clinical text
    // via the Report tab), this button is always visible and lazily triggers
    // that same assembly itself on first click — the profile tab loads
    // immediately on patient search, well before Report's lazy fetch runs.
    async function generatePatientAiSummary() {
        const button = elements.patientAiSummaryBtn;
        if (!getPatientClinicalText()) {
            const card = showAiPreparingPlaceholder(button, null, elements.patientAiSummaryAnchor, 'pre_exam_oneliner');
            await loadReportLazily();
            // loadReportLazily reports its own failures (showOverlayError) and
            // leaves getPatientClinicalText() null; runAiSummary below then
            // surfaces the "no content" toast on its own in that case — but it
            // only does that if button.disabled/the card are reset first,
            // since a failed getText() short-circuits before touching either.
            if (button && !getPatientClinicalText()) {
                card?.remove();
                button.disabled = false;
            }
        }
        runAiSummary(elements.patientAiSummaryBtn, 'pre_exam_oneliner',
            () => null, getPatientClinicalText,
            { inline: true, intoAnchorParent: () => elements.patientAiSummaryAnchor });
    }

    // Lab Trends tab's "Contrast" button (contrast_safety AI prompt — see
    // llm/prompts/contrast_safety.md and buildContrastSafetyText above).
    // Unlike runLabSummary, this needs the patient's clinical record too
    // (for allergy/contrast-reaction flags), which may not be loaded yet if
    // the radiologist opened the Lab tab before the Report tab ever ran —
    // same lazy-load-with-placeholder need as generatePatientAiSummary.
    async function runContrastSafetyCheck() {
        const button = elements.contrastSafetyBtn;
        if (!button) return;
        const anchor = () => elements.trendsContainer?.firstChild || null;
        if (!getPatientClinicalText()) {
            const card = showAiPreparingPlaceholder(button, anchor(), elements.trendsContainer, 'contrast_safety');
            await loadReportLazily();
            if (!getPatientClinicalText()) {
                card?.remove();
                button.disabled = false;
            }
        }
        runAiSummary(button, 'contrast_safety',
            anchor, buildContrastSafetyText,
            { intoAnchorParent: () => elements.trendsContainer, inline: true });
    }

    // opts.force bypasses the server cache and regenerates. opts.checkOnly
    // skips generation entirely — returns null if nothing is cached yet,
    // instead of calling the LLM. Server caches by (kind, sha256(text)), so
    // the same text always redisplays the same summary until forced.
    // Bounds how long the UI can sit on "Waiting for AI response…" with no signal
    // that the connection died silently (a stall with no TCP reset — apiFetch
    // itself has no timeout, since long-running Hipocrate scrapes elsewhere
    // legitimately need to run long). Scoped to just the AI summary requests.
    //
    // Was 45000 (45s) — too short for this server: [llm] log lines show the
    // configured model actually runs at ~2-3.5 tok/s, and imaging_trend/
    // pre_exam_brief prompts run up to ~2000 prompt tokens, so prefill alone
    // (before the *first* streamed chunk arrives, which is what this timer
    // actually gates for aiSummarizeStream — see armTimer()) can easily
    // exceed 45s on its own, well before generation even starts. That was
    // firing the abort mid-prefill on real (not stalled) requests — visible
    // server-side as "ClientConnectionResetError: Cannot write to closing
    // transport" — which also meant the result was never cached (ai_cache is
    // only written after a stream completes), so the same slow request had
    // to be repeated, and re-timed-out, on every retry. 120s comfortably
    // covers observed prefill+first-token latency for the largest prompts
    // while still catching a genuinely dead connection in reasonable time.
    const AI_SUMMARY_TIMEOUT_MS = 120000;
    const AI_TIMEOUT_MESSAGE = 'AI summary timed out — the connection may have been lost. Please try again.';

    async function aiSummarize(kind, text, opts = {}) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), AI_SUMMARY_TIMEOUT_MS);
        let resp, data = {};
        try {
            resp = await apiFetch('/api/ai/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind, text, force: !!opts.force, check_only: !!opts.checkOnly }),
                signal: controller.signal,
            });
            // .json() shares the same AbortSignal as the fetch above, so a
            // stall while reading the body (not just before headers arrive)
            // is covered too — the timer must stay armed until this returns.
            try { data = await resp.json(); } catch (_) { /* non-JSON error */ }
        } catch (err) {
            if (err.name === 'AbortError') throw new Error(AI_TIMEOUT_MESSAGE);
            throw err;
        } finally {
            clearTimeout(timer);
        }
        if (!resp.ok || data.status === 'error') {
            throw new Error(data.message || `AI summary failed (HTTP ${resp.status})`);
        }
        if (data.status === 'not_cached') return null;
        return data.summary || '';
    }

    // Kinds served by /api/ai/summarize with stream:true — every AI-tab kind
    // except imaging, which stays on the plain JSON response above (too
    // short to benefit). Must mirror llm/prompts.py's STREAMING_KINDS.
    const STREAMING_KINDS = new Set([
        'report', 'epicrisis', 'pre_exam_brief', 'lab', 'imaging_trend',
        'pre_exam_soap', 'pre_exam_executive', 'pre_exam_oneliner',
        'contrast_safety',
    ]);

    // Rare sentinel (ASCII Unit Separator) the server uses to signal a
    // mid-stream failure it can no longer report via HTTP status, since the
    // response has already committed to 200 once streaming starts. Must
    // match hippobridge.py's _STREAM_ERROR_SENTINEL exactly.
    const STREAM_ERROR_SENTINEL = '\x1f';

    // Streaming counterpart to aiSummarize(): POSTs to /api/ai/summarize with
    // stream:true and calls onChunk(piece) as text arrives. Always force:true
    // (mirrors runAiSummary's manual-click path, the only caller) — the
    // silent cache-probe path never streams. Throws on error, same contract
    // as aiSummarize(), so callers need no special-casing.
    async function aiSummarizeStream(kind, text, onChunk) {
        // Inactivity timeout, not a flat cap — reset on every chunk, so a
        // slow-but-progressing generation isn't cut off, only a genuine
        // stall (silent connection loss, no TCP reset) trips it. The same
        // AbortSignal covers both the initial fetch and every subsequent
        // reader.read() call, since they share one request/response lifecycle.
        const controller = new AbortController();
        let timer = setTimeout(() => controller.abort(), AI_SUMMARY_TIMEOUT_MS);
        const armTimer = () => {
            clearTimeout(timer);
            timer = setTimeout(() => controller.abort(), AI_SUMMARY_TIMEOUT_MS);
        };

        let resp;
        try {
            resp = await apiFetch('/api/ai/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind, text, force: true, stream: true }),
                signal: controller.signal,
            });
        } catch (err) {
            clearTimeout(timer);
            if (err.name === 'AbortError') throw new Error(AI_TIMEOUT_MESSAGE);
            throw err;
        }
        if (!resp.ok) {
            clearTimeout(timer);
            let data = {};
            try { data = await resp.json(); } catch (_) { /* non-JSON error */ }
            throw new Error(data.message || `AI summary failed (HTTP ${resp.status})`);
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        try {
            while (true) {
                let done, value;
                try {
                    ({ done, value } = await reader.read());
                } catch (err) {
                    if (err.name === 'AbortError') throw new Error(AI_TIMEOUT_MESSAGE);
                    throw err;
                }
                armTimer();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                if (buffer.includes(STREAM_ERROR_SENTINEL)) {
                    const [, , message] = buffer.split(STREAM_ERROR_SENTINEL);
                    throw new Error(message || 'AI summary failed');
                }
                if (buffer) { onChunk(buffer); buffer = ''; }
            }
        } finally {
            clearTimeout(timer);
        }
    }

    // ── Leisure-pace background AI warming ──────────────────────────────
    // Imaging reports lazy-load per card as they scroll into view
    // (IntersectionObserver in renderAnalysesCards). While the radiologist
    // is still reading, quietly pre-generate each one's AI triage summary
    // in the background so it's already cached by the time they click the
    // card's AI button — same /api/ai/summarize cache, this just warms it
    // early. One job at a time with a gap between each, so it never bursts
    // the LLM provider or competes with a real user-triggered request; a
    // stale patient's queued jobs are dropped via the dataGeneration check.
    let aiWarmQueue = [];
    let aiWarmRunning = false;
    let aiWarmPausedUntil = 0;
    const AI_WARM_GAP_MS = 4000;
    const AI_WARM_PAUSE_MS = 5 * 60 * 1000;

    // gen: the dataGeneration the job belongs to (dropped if the patient
    // changed meanwhile), or null for a job that isn't tied to a patient (the
    // schedule's previous-exam summaries). onDone(summary) fires when the job
    // finishes; summary is null when it was skipped, dropped or failed.
    function enqueueAiWarm(kind, text, gen, onDone) {
        if (!text) return;
        if (Date.now() < aiWarmPausedUntil) { onDone?.(null); return; }
        aiWarmQueue.push({ kind, text, gen, onDone });
        if (!aiWarmRunning) processAiWarmQueue();
    }

    async function processAiWarmQueue() {
        aiWarmRunning = true;
        while (aiWarmQueue.length) {
            // Nobody is looking at the page: don't spend LLM time on it
            while (document.hidden) await new Promise(r => setTimeout(r, 3000));
            const job = aiWarmQueue.shift();
            if (job.gen == null || job.gen === dataGeneration) {
                try {
                    job.onDone?.(await aiSummarize(job.kind, job.text));
                } catch (err) {
                    // Likely misconfigured/unreachable — stop trying for a while
                    // rather than burning through the rest of the queue on failures.
                    log('Background AI warm failed, pausing warm queue (silent):', err);
                    aiWarmPausedUntil = Date.now() + AI_WARM_PAUSE_MS;
                    job.onDone?.(null);
                    aiWarmQueue.splice(0).forEach(j => j.onDone?.(null));
                    break;
                }
            } else {
                job.onDone?.(null);
            }
            if (aiWarmQueue.length) await new Promise(r => setTimeout(r, AI_WARM_GAP_MS));
        }
        aiWarmRunning = false;
    }

    function makeAiCard(inline) {
        const card = document.getElementById('ai-card-template').content
            .firstElementChild.cloneNode(true);
        if (inline) card.classList.add('ai-card-inline');
        return card;
    }

    // Human-readable titles shown in the amber disclaimer badge, in place of
    // the bare "AI-generated" — lets a radiologist tell cards apart at a
    // glance (e.g. on the Lab Trends tab, which can show a lab summary and a
    // contrast-risk card at once). Falls back to plain "AI-generated" for any
    // kind not listed here.
    const AI_KIND_LABELS = {
        report:              'Patient summary',
        epicrisis:            'Epicrisis summary',
        imaging:              'Report summary',
        imaging_trend:        'Imaging trend',
        lab:                  'Lab summary',
        pre_exam_oneliner:    'Pre-exam one-liner',
        pre_exam_brief:       'Pre-exam brief',
        pre_exam_executive:   'Pre-exam executive summary',
        pre_exam_soap:        'Pre-exam SOAP note',
        contrast_safety:      'Contrast agent risk',
    };

    function setAiCardBadgeTitle(card, kind) {
        const titleEl = card?.querySelector('.ai-summary-badge-title');
        if (!titleEl) return;
        const label = AI_KIND_LABELS[kind];
        titleEl.textContent = label ? `${label} — AI-generated` : 'AI-generated';
    }

    function wireAiCardCopy(card) {
        const copyBtn = card.querySelector('.btn-ai-copy');
        const body = card.querySelector('.ai-summary-body');
        if (copyBtn && body) {
            copyBtn.addEventListener('click', () => copyMarkdown(body, copyBtn, () => flashIcon(copyBtn)));
        }
    }

    function stripOuterFence(text) {
        if (!text) return text;
        const lines = text.split('\n');
        const fenceRe = /^```\w*\s*$/;
        if (lines.length > 2 && fenceRe.test(lines[0].trimEnd()) && fenceRe.test(lines[lines.length - 1].trimStart())) {
            return lines.slice(1, -1).join('\n').trimStart();
        }
        return text;
    }

    // Place `card` immediately before `anchor`; if the anchor is missing but
    // an `intoParent` container is given, prepend into it instead.
    function placeAiCard(card, anchor, intoParent) {
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(card, anchor);
        } else if (intoParent) {
            intoParent.insertBefore(card, intoParent.firstChild);
        }
    }

    // Generic click handler: (re)insert the button's card in loading state,
    // fetch the summary, render it as markdown, or show an error in-card.
    // opts.auto: silent cache-only probe (used on page/tab load to redisplay
    // a previously generated summary) — no spinner, no toast on miss, and it
    // never calls the LLM. A real click always forces regeneration.
    // Deterministic intro line for the Pre-Exam card — the prompt itself is
    // forbidden from stating age/sex (small models fabricate them when asked
    // to restate demographics from free text; see getPatientClinicalText
    // above), so the real identity is spliced in here from the already-loaded,
    // trustworthy patient record instead, the same way buildImagingCardHeader
    // grounds an imaging card. Prepended to the rendered markdown, never sent
    // to the LLM.
    function buildPreExamHeader() {
        const patientData = pendingAnalysesData?.patientData;
        if (!patientData) return '';
        const name = formatPatientName(patientData);
        const age = calculateAge(patientData.birth_date);
        const gender = formatGender(patientData.sex);
        const dob = formatBirthDate(patientData.birth_date);
        const parts = [];
        if (name && name !== 'N/A') parts.push(`**${name}**`);
        const demo = [gender, age].filter(v => v && v !== 'N/A').join(', ');
        if (demo) parts.push(demo);
        if (dob && dob !== 'N/A') parts.push(`DOB ${dob}`);
        if (!parts.length) return '';
        return parts.join(' · ') + '\n\n---\n\n';
    }

    async function runAiSummary(button, kind, getAnchor, getText, opts = {}) {
        if (!button) return;
        const text = (getText() || '').trim();
        if (!text) {
            if (!opts.auto) showToast('No content available for AI summary', 'warning');
            return;
        }

        let card = button._aiCard;
        if (!card || !card.isConnected) {
            card = makeAiCard(opts.inline);
            wireAiCardCopy(card);
            button._aiCard = card;
        }
        setAiCardBadgeTitle(card, kind);

        if (opts.auto) {
            try {
                const cached = await aiSummarize(kind, text, { checkOnly: true });
                if (cached === null) return; // nothing cached yet — leave the button untouched
                placeAiCard(card, getAnchor(), opts.intoAnchorParent?.());
                const body = card.querySelector('.ai-summary-body');
                card.classList.remove('ai-card-error');
                body.classList.remove('ai-summary-loading');
                const header = kind.startsWith('pre_exam_') && kind !== 'pre_exam_oneliner' ? buildPreExamHeader() : '';
                const shown = header + (cached || '_(empty response)_');
                body.innerHTML = marked.parse(stripOuterFence(shown));
                body.dataset.markdown = shown;
            } catch (_) {
                // Silent — an auto-probe failure shouldn't surface to the user.
            }
            return;
        }

        placeAiCard(card, getAnchor(), opts.intoAnchorParent?.());

        const body = card.querySelector('.ai-summary-body');
        card.classList.remove('ai-card-error');
        body.classList.add('ai-summary-loading');
        body.textContent = 'Waiting for AI response…';
        button.disabled = true;
        try {
            if (STREAMING_KINDS.has(kind)) {
                let full = '';
                let first = true;
                await aiSummarizeStream(kind, text, (piece) => {
                    if (first) {
                        // First chunk arrived — drop the "Waiting for data…"
                        // placeholder and render plain text incrementally.
                        // No partial-Markdown parsing: a half-finished
                        // "### heading" or "**bold" mid-stream renders broken,
                        // so the full Markdown pass only happens once, below,
                        // after the stream completes.
                        body.classList.remove('ai-summary-loading');
                        body.classList.add('ai-summary-streaming');
                        body.textContent = '';
                        first = false;
                    }
                    full += piece;
                    body.textContent = full;
                });
                body.classList.remove('ai-summary-streaming');
                const header = kind.startsWith('pre_exam_') && kind !== 'pre_exam_oneliner' ? buildPreExamHeader() : '';
                const shown = header + (full || '_(empty response)_');
                body.innerHTML = marked.parse(stripOuterFence(shown));
                body.dataset.markdown = shown;
            } else {
                const summary = await aiSummarize(kind, text, { force: true });
                body.classList.remove('ai-summary-loading');
                const header = kind.startsWith('pre_exam_') && kind !== 'pre_exam_oneliner' ? buildPreExamHeader() : '';
                const shown = header + (summary || '_(empty response)_');
                body.innerHTML = marked.parse(stripOuterFence(shown));
                body.dataset.markdown = shown;
            }
        } catch (err) {
            console.error(`AI summary failed (${kind}):`, err);
            body.classList.remove('ai-summary-loading', 'ai-summary-streaming');
            card.classList.add('ai-card-error');
            body.textContent = `AI summary failed: ${err.message}`;
            body.dataset.markdown = `AI summary failed: ${err.message}`;
        } finally {
            button.disabled = false;
        }
    }

    function wireAiButton(button, kind, getAnchor, getText, opts = {}) {
        if (!button) return;
        button.addEventListener('click', () => runAiSummary(button, kind, getAnchor, getText, opts));
    }

    // Builds one button per PRE_EXAM_TOOLBAR entry into elements.aiPreExamToolbar
    // (mirrors buildImagingEpisodeHeader's manual document.createElement
    // pattern — no <template> needed since these buttons carry no ids).
    // Returns the created buttons so callers can toggle/reset them as a group.
    function buildAiPreExamToolbar() {
        if (!elements.aiPreExamToolbar) return [];
        return PRE_EXAM_TOOLBAR.map(cfg => {
            const btn = document.createElement('button');
            btn.className = 'btn-ai';
            btn.hidden = true;
            btn.dataset.kind = cfg.kind;
            btn.setAttribute('aria-label', `Generate ${cfg.label}`);
            btn.title = `Generate ${cfg.label}`;
            const icon = document.createElement('i');
            icon.className = `fas ${cfg.icon}`;
            icon.setAttribute('aria-hidden', 'true');
            const span = document.createElement('span');
            span.textContent = cfg.label;
            btn.append(icon, span);
            elements.aiPreExamToolbar.appendChild(btn);
            wireAiButton(btn, cfg.kind, () => elements.aiPreExamAnchor, () => getPatientClinicalText());
            return btn;
        });
    }

    // Lab Trends button — sends only the pathological rows to the model. When
    // nothing is out of range, skip the call and render a direct "all normal"
    // card (no amber "AI-generated" badge, since it's a deterministic check).
    async function runLabSummary() {
        const button = elements.aiLabBtn;
        if (labHasAbnormal) {
            return runAiSummary(button, 'lab',
                () => elements.trendsContainer?.firstChild || null, () => labAiText,
                { intoAnchorParent: () => elements.trendsContainer, inline: true });
        }
        let card = button._aiCard;
        if (!card || !card.isConnected) {
            card = makeAiCard(true);
            wireAiCardCopy(card);
            button._aiCard = card;
        }
        placeAiCard(card, elements.trendsContainer?.firstChild || null, elements.trendsContainer);
        card.classList.remove('ai-card-error');
        const badge = card.querySelector('.ai-summary-badge');
        if (badge) badge.hidden = true;
        const body = card.querySelector('.ai-summary-body');
        body.classList.remove('ai-summary-loading');
        body.innerHTML = marked.parse(stripOuterFence('**All lab values are within their reference intervals.**'));
        body.dataset.markdown = '**All lab values are within their reference intervals.**';
    }

    async function loadAndDisplayReport(patientData, analysesData) {
        log('Loading and displaying report data');
        
        // Display patient report with analyses and epicrisis
        await displayPatientReport(patientData, analysesData);
        
                
        log('Report data loading complete');
    }
    
    async function populateAnalysesMarkdown(analysesData) {
        log('Populating analyses by modality');
        
        // Define modality mapping
        const modalityMap = {
            'radio': { name: 'X-Ray',       icon: 'mod-radio'  },
            'ct':    { name: 'CT',          icon: 'mod-ct'     },
            'irm':   { name: 'MRI',         icon: 'mod-irm'    },
            'eco':   { name: 'Ultrasound',  icon: 'mod-eco'    },
            'rads':  { name: 'Fluoroscopy', icon: 'mod-fluoro' },
        };
        
        // Group analyses by modality
        const analysesByModality = {};
        
        if (analysesData.requests && analysesData.requests.length > 0) {
            analysesData.requests.forEach(serviceRequest => {
                const analysisType = serviceRequest.type || 'unknown';
                const analysisText = serviceRequest.type_display || 'analysis';
                // Skip unknown types
                if (!modalityMap[analysisType]) return;

                if (!analysesByModality[analysisType]) {
                    analysesByModality[analysisType] = [];
                }

                analysesByModality[analysisType].push({
                    serviceRequest,
                    analysisType,
                    analysisText,
                    examDateString: serviceRequest.date_time || null
                });
            });
        }

        // Sort each modality group by date string (most recent first)
        Object.keys(analysesByModality).forEach(modality => {
            analysesByModality[modality].sort((a, b) => {
                if (!a.examDateString || !b.examDateString) return 0;
                return b.examDateString > a.examDateString ? 1 : -1;
            });
        });
        
        // Generate markdown content
        let markdown = '';

        if (Object.keys(analysesByModality).length === 0) {
            return '';
        }

        markdown += '## Imaging Studies\n\n';

        for (const modality of Object.keys(analysesByModality)) {
            const modalityInfo = modalityMap[modality];
            const analyses = analysesByModality[modality];

            markdown += `### ${modalityInfo.name} (${analyses.length})\n\n`;

            const reportContents = await limitedMap(
                analyses,
                MAX_CONCURRENT_REQUESTS,
                a => getReportContent(a.serviceRequest.id, a.analysisType)
            );

            analyses.forEach((analysis, idx) => {
                const formattedDate = analysis.examDateString ?
                    formatDateWithTime(analysis.examDateString) : 'Unknown date';

                markdown += `#### ${analysis.analysisText} — ${formattedDate}\n\n`;

                const reportContent = reportContents[idx];
                if (reportContent) {
                    markdown += reportContent.trim() + '\n';
                } else {
                    markdown += '_No report text available._\n';
                }

                markdown += '\n---\n\n';
            });
        }
        
        log('Analyses by modality markdown generated successfully');
        return markdown;
    }
    
    // View of a report from /api/study/{id} (imaging) or /api/report/{id} (lab
    // and other): header facts (date, requester, indication, examiner) plus the
    // reported content — `results` [{title, text}] per reported study for
    // imaging, `forms` (rows for buildLabTable/buildLabMarkdown) otherwise.
    // `indication` is the request's clinical indication as merged server-side.
    function reportFromApi(d, isImaging) {
        const studies = d?.studies || [];
        const reported = studies.filter(s => s.result);
        const v = { date: '', requester: '', indication: '', examiner: '', results: [], forms: [] };
        if (isImaging) {
            v.date = d?.request?.date_time || '';
            v.requester = d?.checkin?.medic || '';
            v.indication = d?.request?.justification || '';
            // Signing physician; falls back to the requester server-side-style
            // when no validator is recorded, so callers only show it once a
            // report actually exists.
            v.examiner = studies[0]?.validator || d?.checkin?.medic || '';
            v.results = reported.map(s => ({ title: s.title || '', text: s.result }));
        } else {
            v.date = d?.study?.date_time || d?.request?.date_time || d?.checkin?.date_time || '';
            v.indication = d?.request?.clinical_comments || '';
            v.forms = reported.map(s => ({
                contentType: 'text/markdown', title: s.title || '', data: s.result,
                type: s.type || '', region: s.region || '', reference: s.reference || '',
                section: s.section || '', flag: s.flag,
            }));
        }
        return v;
    }

    // Helper function to get report content for a service request
    const IMAGING_TYPES = ['radio', 'ct', 'irm', 'eco', 'rads'];
    async function getReportContent(serviceRequestId, analysisType) {
        // check cache first
        if (cache.reports[serviceRequestId]) {
            return cache.reports[serviceRequestId];
        }

        try {
            const isImaging = IMAGING_TYPES.includes(analysisType);
            const endpoint = isImaging
                ? `/api/study/${serviceRequestId}`
                : `/api/report/${serviceRequestId}`;
            const reportResponse = await apiFetch(endpoint);

            if (!reportResponse.ok) {
                log(`Report not found for service request ${serviceRequestId}`);
                return null;
            }

            const report = reportFromApi(await reportResponse.json(), isImaging);
            let content = null;
            if (isImaging) {
                content = [report.indication, ...report.results.map(r => r.text)]
                    .filter(Boolean).join('\n\n').trim();
            } else if (report.forms.length > 0) {
                const forms = report.forms;
                const multiStudy = forms.length > 1;
                content = forms
                    .filter(f => f.data)
                    .map(f => multiStudy && f.title ? `##### ${f.title}\n\n${f.data}` : f.data)
                    .join('\n\n---\n\n')
                    .trim();
            }

            // only cache non-empty results; null/empty means report not written yet
            if (content) cachePut(cache.reports, serviceRequestId, content);
            return content;
            
        } catch (error) {
            console.error(`Error fetching report content for service request ${serviceRequestId}:`, error);
            return null;
        }
    }
    
    // Fetch an ImagingStudy and split its notes into the clinical indication
    // (the ordering justification) and the actual report body. Mirrors the
    // separation done in the analyses-tab card so the indication never leaks
    // into the report text.
    async function getImagingReportParts(serviceRequestId) {
        try {
            const resp = await apiFetch(`/api/study/${serviceRequestId}`);
            if (!resp.ok) return { indication: '', body: '' };
            const report = reportFromApi(await resp.json(), true);
            const indication = report.indication.trim();
            const body = report.results.map(r => r.text).filter(Boolean).join('\n\n').trim();
            // Signing/reporting physician. Only meaningful once a report
            // actually exists: without one, the examiner falls back to the
            // requesting physician, which would misattribute the
            // (nonexistent) report.
            const physician = body ? report.examiner : '';
            return { indication, body, physician };
        } catch (error) {
            console.error(`Error fetching imaging report parts for ${serviceRequestId}:`, error);
            return { indication: '', body: '', physician: '' };
        }
    }

    async function generateEpicrisisMarkdown(patientData) {
        log('Generating epicrisis markdown');

        const checkoutIds = extractCheckoutIds(patientData);
        if (checkoutIds.length === 0) return '';

        const epicrisisData = [];

        const encounters = await limitedMap(
            checkoutIds,
            MAX_CONCURRENT_REQUESTS,
            async id => {
                try { return await fetchEncounterDataForCheckout(id); }
                catch (err) { return null; }
            }
        );

        encounters.forEach((encounterData, idx) => {
            if (!encounterData) return;
            const epicrisisText = extractEpicrisisText(encounterData);
            if (!epicrisisText) return;
            epicrisisData.push({
                checkoutId: checkoutIds[idx],
                diagnosis: extractDiagnosisText(encounterData),
                admissionDate: encounterData.start || null,
                dischargeDate: encounterData.end   || null,
                attender: encounterData.attender || null,
                service: encounterData.service || null,
                epicrisisText,
            });
        });

        epicrisisData.sort((a, b) => {
            if (!a.dischargeDate || !b.dischargeDate) return 0;
            return b.dischargeDate > a.dischargeDate ? 1 : -1;
        });

        if (epicrisisData.length === 0) return '';

        let markdown = '## Discharge Summaries\n\n';

        epicrisisData.forEach((ep, index) => {
            const dischargeStr  = ep.dischargeDate  ? formatDate(ep.dischargeDate)  : 'unknown';
            const admissionStr  = ep.admissionDate  ? formatDate(ep.admissionDate)  : 'unknown';
            const diagnosis     = ep.diagnosis || 'Unspecified';

            markdown += `### ${index + 1}. ${diagnosis} — ${dischargeStr}\n\n`;
            markdown += `**Admission:** ${admissionStr} · **Discharge:** ${dischargeStr}`;
            if (ep.attender) markdown += ` · **Attending:** ${ep.attender}`;
            if (ep.service)  markdown += ` · **Service:** ${ep.service}`;
            markdown += `  \n\n`;
            markdown += ep.epicrisisText.trim();
            markdown += '\n\n---\n\n';
        });

        log('Epicrisis markdown generated successfully');
        return markdown;
    }

    // ── Clinical-text size budget for the on-site LLM ─────────────────────
    // The assembled clinical text (admissions + labs + imaging) is sent
    // verbatim as the AI tab's "report"/"pre_exam_brief" input, sharing an ~8k
    // token context window with the system prompt and the model's own
    // output. Nothing tokenizes client-side, so this is a conservative
    // chars-per-token approximation (Romanian medical text with diacritics
    // tokenizes worse than plain English), not an exact count. This budget
    // only trims the copy sent to the LLM — the full, untrimmed markdown
    // still goes into the Report tab's own display/copy button.
    const CLINICAL_TEXT_TOKEN_BUDGET = 8000;
    // Reserve: largest system prompt among clinicalMarkdown's consumers
    // (pre_exam_brief.md, ~1350 tokens) + its max_tokens (450, see
    // llm/prompts.py PROMPT_META) + the date/language directives appended
    // at call time + a safety margin. Bump this if either grows a lot.
    const CLINICAL_TEXT_RESERVED_TOKENS = 2200;
    const CLINICAL_TEXT_CHARS_PER_TOKEN = 3.5;
    const CLINICAL_TEXT_CHAR_BUDGET =
        (CLINICAL_TEXT_TOKEN_BUDGET - CLINICAL_TEXT_RESERVED_TOKENS) * CLINICAL_TEXT_CHARS_PER_TOKEN;

    // Greedily keeps candidates in priority order (lower `priority` = more
    // important, considered first) until the char budget runs out, then
    // re-joins the survivors in their original array order — so a
    // lower-priority block never displaces a higher-priority one, but nothing
    // gets cut mid-sentence: each candidate is included whole or not at all.
    function fitClinicalTextToBudget(candidates, budgetChars) {
        const byPriority = [...candidates].sort((a, b) => a.priority - b.priority);
        const kept = new Set();
        let used = 0;
        for (const c of byPriority) {
            if (!c.text) continue;
            if (used + c.text.length > budgetChars) continue;
            kept.add(c);
            used += c.text.length;
        }
        return candidates.filter(c => kept.has(c)).map(c => c.text).join('');
    }

    async function displayPatientReport(patientData, analysesData) {
        log('Displaying patient report data');

        const reportCard = elements.reportCard;
        const markdownStore = elements.patientReportMarkdown;
        if (reportCard) reportCard.hidden = true;

        try {
            // ── §1 Patient identity ──────────────────────────────────────
            const name     = formatPatientName(patientData);
            const age      = calculateAge(patientData.birth_date);
            const gender   = formatGender(patientData.sex);
            const dob      = formatBirthDate(patientData.birth_date);
            const cnp      = patientData.cnp || '';
            const pid      = patientData.id || '';

            const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            const eyebrowEl = document.getElementById('reportEyebrow');
            if (eyebrowEl) eyebrowEl.textContent = `Clinical Report · ${name}`;
            const patientLineEl = document.getElementById('reportPatientLine');
            if (patientLineEl) {
                patientLineEl.innerHTML = '';
                patientLineEl.append(name);
                const meta = [gender, dob ? age : ''].filter(Boolean).join(' · ');
                if (meta) {
                    const metaSpan = document.createElement('span');
                    metaSpan.className = 'report-patient-meta';
                    metaSpan.textContent = ` · ${meta}`;
                    patientLineEl.appendChild(metaSpan);
                }
            }
            setText('reportCNP', cnp);

            const patHippoUrl = patientHipocrateUrl(patientData);
            const pidWrap = document.getElementById('reportPatientIdWrap');
            if (pidWrap) {
                pidWrap.innerHTML = '';
                if (pid && patHippoUrl) {
                    const a = document.createElement('a');
                    a.href = patHippoUrl;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.textContent = pid;
                    pidWrap.appendChild(a);
                } else {
                    pidWrap.textContent = pid;
                }
            }

            const weight = patientData.weight || '';
            const height = patientData.height || '';
            const weightWrap = document.getElementById('reportWeightWrap');
            const heightWrap = document.getElementById('reportHeightWrap');
            if (weight && weightWrap) { document.getElementById('reportWeight').textContent = weight + ' kg'; weightWrap.hidden = false; }
            else if (weightWrap) weightWrap.hidden = true;
            if (height && heightWrap) { document.getElementById('reportHeight').textContent = height + ' cm'; heightWrap.hidden = false; }
            else if (heightWrap) heightWrap.hidden = true;

            // ── §2 + §4 Encounters (parallel with analyses) ──────────────
            const analysesDates = (analysesData?.requests || []).map(e => e.date_time).filter(Boolean);
            const [analysesMarkdown, epicrisisMarkdown, episodeInfo] = await Promise.all([
                analysesData ? populateAnalysesMarkdown(analysesData) : Promise.resolve(''),
                generateEpicrisisMarkdown(patientData),
                getEpisodeBoundary(patientData, analysesDates),
            ]);
            const { encounters, activeAdm, lastDischarge, boundaryDate, source: boundarySource } = episodeInfo;

            // Primary diagnosis from most recent encounter
            const latestDx = encounters[0] ? extractDiagnosisText(encounters[0].enc) : '';
            setText('reportDiagnosis', latestDx);

            // §2 Admission
            // Active inpatient → Current Admission block.
            // Most recent discharged with epicrisis → Last Admission block.
            // Last Admission is also shown for outpatients, and for inpatients whose
            // checkin text is sparse (< 100 chars), so there is always useful context.
            const SPARSE_THRESHOLD = 100;

            function buildCheckinText(enc) {
                const parts = [];
                const dx = extractDiagnosisText(enc);
                if (dx) parts.push(dx);
                (enc.notes || []).forEach(text => {
                    if (!text) return;
                    const clean = text
                        .replace(/^\[Exam general\]\s*/i, '')
                        .replace(/^\[Exam local\]\s*/i, '')
                        .trim();
                    if (clean) parts.push(clean);
                });
                return parts.join('\n\n');
            }

            function fillAdmissionBlock(secId, periodId, textId, enc, isActive) {
                const sec = document.getElementById(secId);
                if (!sec) return;
                const start = enc.start ? formatDate(enc.start) : '';
                const end   = enc.end   ? formatDate(enc.end)   : '';
                const ms    = (enc.start && enc.end)
                    ? new Date(enc.end) - new Date(enc.start) : 0;
                const nights = ms > 0 ? Math.round(ms / 86400000) : 0;
                const periodEl = document.getElementById(periodId);
                if (periodEl) {
                    periodEl.textContent = isActive
                        ? `${start} → present (ongoing)`
                        : `${start} → ${end}${nights ? ` (${nights} ${nights === 1 ? 'night' : 'nights'})` : ''}`;
                }
                const textEl = document.getElementById(textId);
                if (textEl) {
                    const body = isActive
                        ? buildCheckinText(enc)
                        : extractEpicrisisText(enc).trim();
                    textEl.innerHTML = marked.parse(body);
                }
                sec.hidden = false;
            }

            // activeAdm/lastDischarge come from the shared computeCurrentEpisodeBoundary
            // helper (episodeInfo above) — see its comment for the "in-progress can be
            // stale" rationale; this is display-only usage of that already-computed data.
            const secAdmission = document.getElementById('reportSectionAdmission');
            const secLastAdmission = document.getElementById('reportSectionLastAdmission');
            if (secAdmission) secAdmission.hidden = true;
            if (secLastAdmission) secLastAdmission.hidden = true;

            if (activeAdm) {
                fillAdmissionBlock('reportSectionAdmission', 'reportAdmissionPeriod', 'reportAdmissionText', activeAdm.enc, true);
                // Also show last discharge if checkin text is sparse
                const checkinBody = buildCheckinText(activeAdm.enc);
                if (checkinBody.length < SPARSE_THRESHOLD && lastDischarge) {
                    fillAdmissionBlock('reportSectionLastAdmission', 'reportLastAdmissionPeriod', 'reportLastAdmissionText', lastDischarge.enc, false);
                }
            } else if (lastDischarge) {
                // Outpatient — show last admission only
                fillAdmissionBlock('reportSectionLastAdmission', 'reportLastAdmissionPeriod', 'reportLastAdmissionText', lastDischarge.enc, false);
            }

            // §3 Recent imaging — up to 5 most recent entries from the current
            // episode (scoped by boundaryDate; falls back to unfiltered
            // most-recent when there's no episode signal at all).
            const secImaging = document.getElementById('reportSectionImaging');
            const imagingList = document.getElementById('reportImagingList');
            if (secImaging) secImaging.hidden = true;
            const MOD_SHORT = { radio: 'XR', ct: 'CT', irm: 'MR', eco: 'US', rads: 'FL', fluoro: 'FL' };
            const MOD_VAR   = { radio: '--mod-xr', ct: '--mod-ct', irm: '--mod-mr', eco: '--mod-us', rads: '--mod-fl', fluoro: '--mod-fl' };
            // Hoisted so the markdown builder below can reference them
            let entries = [], reports = [], indications = [];
            if (imagingList && analysesData?.requests?.length) {
                const candidates = [...analysesData.requests]
                    .filter(e => MOD_SHORT[e.type])
                    .filter(e => !boundaryDate || (e.date_time || '') >= boundaryDate)
                    .sort((a, b) => (b.date_time || '') > (a.date_time || '') ? 1 : -1)
                    .slice(0, 20); // fetch more than needed so we can skip empty ones

                const candidateReports = await limitedMap(candidates, MAX_CONCURRENT_REQUESTS,
                    sr => getImagingReportParts(sr.id));

                // Keep entries that have a report or a clinical indication, up to 5
                const physicians = [];
                for (let i = 0; i < candidates.length && entries.length < 5; i++) {
                    const { body, indication, physician } = candidateReports[i];
                    if (body || indication) {
                        entries.push(candidates[i]);
                        reports.push(body);
                        indications.push(indication);
                        physicians.push(physician);
                    }
                }

                imagingList.innerHTML = '';
                entries.forEach((sr, idx) => {
                    const mod  = sr.type || '';
                    const desc = sr.type_display || MODALITY_INFO[mod]?.label || mod;
                    const date = sr.date_time ? formatDate(sr.date_time) : '';
                    const code = sr.id || '';
                    const isUrgent = !!sr.is_urgent;
                    const physician = physicians[idx] || '';
                    const reportText = reports[idx] || '';
                    const indication = indications[idx] || '';
                    const regions = (sr.regions || []).filter(Boolean).join(', ');

                    const row = document.createElement('div');
                    row.className = 'report-imaging-row';

                    const header = document.createElement('div');
                    header.className = 'report-imaging-header';

                    const badge = document.createElement('span');
                    badge.className = 'report-mod-badge';
                    badge.style.setProperty('--mod-color', `var(${MOD_VAR[mod]})`);
                    badge.textContent = MOD_SHORT[mod] || mod.toUpperCase();

                    // Title block mirrors the analyses card: name · regions · indication
                    // on the heading line, exam date + id as the subtitle line.
                    const titleBlock = document.createElement('hgroup');
                    titleBlock.className = 'report-imaging-titleblock';

                    const title = document.createElement('h4');
                    title.className = 'report-imaging-title';
                    const name = document.createElement('span');
                    name.className = 'report-imaging-name';
                    name.textContent = desc;
                    title.appendChild(name);
                    if (regions) {
                        const reg = document.createElement('span');
                        reg.className = 'report-imaging-regions';
                        reg.textContent = ` · ${regions}`;
                        title.appendChild(reg);
                    }
                    if (indication) {
                        const ind = document.createElement('em');
                        ind.className = 'report-imaging-indication';
                        ind.textContent = ` · ${indication}`;
                        title.appendChild(ind);
                    }

                    const meta = document.createElement('p');
                    meta.className = 'report-imaging-meta';
                    meta.textContent = [date, code ? '#' + code : ''].filter(Boolean).join(' · ');

                    titleBlock.append(title, meta);
                    header.append(badge, titleBlock);

                    if (isUrgent) {
                        const urg = document.createElement('span');
                        urg.className = 'report-urgent-tag';
                        urg.textContent = 'URGENT';
                        header.appendChild(urg);
                    }

                    row.appendChild(header);

                    if (reportText) {
                        const div = document.createElement('div');
                        div.className = 'report-imaging-text';
                        div.innerHTML = marked.parse(reportText);
                        row.appendChild(div);
                    }

                    if (physician) {
                        // Reporting/signing physician (resultsInterpreter, falling
                        // back to performer) — who authored the report text above,
                        // not who ordered the exam.
                        const sig = document.createElement('div');
                        sig.className = 'report-imaging-sig';
                        sig.setAttribute('aria-label', 'Reporting physician');
                        const sigIcon = document.createElement('i');
                        sigIcon.className = 'fas fa-signature';
                        sigIcon.setAttribute('aria-hidden', 'true');
                        sig.appendChild(sigIcon);
                        sig.append(` ${physician}`);
                        row.appendChild(sig);
                    }

                    imagingList.appendChild(row);
                });
                if (secImaging) secImaging.hidden = false;
            }

            // §4 Recent labs (compact) ───────────────────────────────────
            // Distinct from the dedicated Lab tab's fuller trend table: a
            // short "## Recent Labs" section for the report/epicrisis/
            // pre_exam_brief clinical text, which previously never saw any lab
            // data at all (pre_exam_brief's own prompt already claims to use
            // "labs" — this fulfils that). Scoped to the current/last
            // hospitalization period (not a fixed lookback window) — only
            // modified (out-of-range) analytes, last value per analyte,
            // grouped by date. Reference range is omitted here on purpose:
            // the H/L flag + colour already say "abnormal"; the exact normal
            // range is one tap away in the dedicated Lab tab.
            function isAbnormalObservation(obs) {
                if (obs.flag === 'H' || obs.flag === 'L') return true;
                const v = obs.value;
                if (v == null) return false;
                const low = obs.low;
                const high = obs.high;
                return (low != null && v < low) || (high != null && v > high);
            }

            // One row per modified (out-of-range) analyte, last value only,
            // grouped by date so a same-day panel doesn't repeat its date.
            function collectLabItems(observations) {
                // Keyed by section+name — the same analyte name can appear under
                // different sections (e.g. "Glucoza" in blood chemistry vs. urine),
                // and without the section prefix a value from one would wrongly
                // overwrite the other as "the latest" for that name.
                const latestNumeric = new Map();
                for (const obs of observations) {
                    const name = obs.analyte;
                    const date = obs.date || '';
                    const section = obs.section || '';
                    if (!name || !date || obs.value == null) continue;
                    const key = `${section} ${name}`;
                    const prev = latestNumeric.get(key);
                    if (!prev || date > prev.date) latestNumeric.set(key, { obs, date, section });
                }
                const items = [];
                for (const { obs, date, section } of latestNumeric.values()) {
                    if (!isAbnormalObservation(obs)) continue;
                    const v = obs.value;
                    const unit = obs.unit || '';
                    const flag = obs.flag
                        || (obs.low != null && v < obs.low ? 'L'
                            : obs.high != null && v > obs.high ? 'H' : '');
                    items.push({ name: obs.analyte, date, section, value: `${v}${unit ? ' ' + unit : ''}`, flag });
                }
                // Section, then most-recent date first within each section.
                items.sort((a, b) => a.section.localeCompare(b.section) || b.date.localeCompare(a.date));
                return items;
            }

            function labItemsToMarkdown(items) {
                if (!items.length) return '';
                let md = '## Recent Labs\n\n';
                let lastSection = null, lastDate = null;
                for (const item of items) {
                    if (item.section !== lastSection) {
                        if (lastSection !== null) md += '\n';
                        md += `### ${item.section || 'Other'}\n\n`;
                        lastSection = item.section;
                        lastDate = null;
                    }
                    if (item.date !== lastDate) {
                        if (lastDate !== null) md += '\n';
                        md += `**${formatDate(item.date)}**\n\n`;
                        lastDate = item.date;
                    }
                    md += `- ${item.name}: ${item.value}${item.flag ? ` (${item.flag})` : ''}\n`;
                }
                return md + '\n';
            }

            function renderLabsTable(items) {
                const wrap = document.createElement('div');
                wrap.className = 'lab-result-wrap';
                let lastSection = null, lastDate = null;
                let tbody = null;
                for (const item of items) {
                    if (item.section !== lastSection) {
                        const secHeading = document.createElement('h4');
                        secHeading.className = 'lab-section-heading';
                        secHeading.textContent = item.section || 'Other';
                        wrap.appendChild(secHeading);
                        lastSection = item.section;
                        lastDate = null;
                    }
                    if (item.date !== lastDate) {
                        const heading = document.createElement('p');
                        heading.className = 'lab-date-heading';
                        heading.textContent = formatDate(item.date);
                        wrap.appendChild(heading);
                        const table = document.createElement('table');
                        table.className = 'lab-result-table';
                        tbody = table.createTBody();
                        wrap.appendChild(table);
                        lastDate = item.date;
                    }
                    const row = tbody.insertRow();
                    const tdName = row.insertCell();
                    tdName.className = 'lab-name';
                    tdName.textContent = item.name;
                    const tdVal = row.insertCell();
                    tdVal.className = 'lab-value' + (item.flag === 'H' ? ' lab-high' : item.flag === 'L' ? ' lab-low' : '');
                    tdVal.textContent = item.value;
                    if (item.flag) {
                        tdVal.appendChild(document.createTextNode(' '));
                        const badge = document.createElement('span');
                        badge.className = 'lab-flag lab-flag-' + item.flag.toLowerCase();
                        badge.textContent = item.flag;
                        tdVal.appendChild(badge);
                    }
                }
                return wrap;
            }

            let labsMd = '';
            let labItems = [];
            try {
                // Scope to the current episode boundary (admission-, discharge-,
                // or gap-cluster-derived) rather than a fixed lookback window —
                // an ongoing admission or cluster has no end yet. Only a closed
                // discharge has a natural end date.
                const periodStart = boundaryDate;
                const periodEnd = boundarySource === 'discharge' ? lastDischarge?.enc.end : undefined;
                if (periodStart) {
                    const params = new URLSearchParams({ patient: pid, start_date: localDateStr(new Date(periodStart)) });
                    if (periodEnd) params.set('end_date', localDateStr(new Date(periodEnd)));
                    const labResp = await apiFetch(`/api/observation?${params}`);
                    if (labResp.ok) {
                        const labData = await labResp.json();
                        labItems = collectLabItems(labData.observations || []);
                        labsMd = labItemsToMarkdown(labItems);
                    }
                }
            } catch (_) {
                // Labs are supplementary here — don't fail the whole report
                // over a lab-fetch error; the dedicated Lab tab still works.
            }

            const secLabs = document.getElementById('reportSectionLabs');
            const labsListEl = document.getElementById('reportLabsList');
            if (secLabs) secLabs.hidden = true;
            if (labsListEl && labItems.length) {
                labsListEl.innerHTML = '';
                labsListEl.appendChild(renderLabsTable(labItems));
                if (secLabs) secLabs.hidden = false;
            }

            // §5 Hospitalisation timeline
            const secTimeline = document.getElementById('reportSectionTimeline');
            const timelineEl  = document.getElementById('reportTimeline');
            if (secTimeline) secTimeline.hidden = true;
            if (timelineEl && encounters.length) {
                timelineEl.innerHTML = '';
                encounters.forEach((item, idx) => {
                    const enc   = item.enc;
                    const start = enc.start ? formatDate(enc.start) : '';
                    const end   = enc.end   ? formatDate(enc.end)   : '';
                    if (!start && !end) return; // skip entries with no date
                    const rawDx = extractDiagnosisText(enc) || '';
                    const dx    = rawDx === '-' ? '' : rawDx;
                    const service = enc.service || enc.wards?.slice(-1)[0] || '';
                    const epicText = extractEpicrisisText(enc);

                    const row = document.createElement('div');
                    row.className = 'report-timeline-row';

                    const dot = document.createElement('span');
                    dot.className = 'report-tl-dot' + (idx < 2 ? ' report-tl-dot-accent' : '');

                    const span = document.createElement('span');
                    span.className = 'report-tl-range';
                    span.textContent = end ? `${start}→${end}` : start;

                    const label = document.createElement('span');
                    const dxShort = dx ? dx.split(' ').slice(1).join(' ') : '';
                    label.textContent = [service, dxShort].filter(Boolean).join(' — ') || dx;

                    row.append(dot, span, label);
                    timelineEl.appendChild(row);

                    if (epicText && idx === 0) {
                        // show first line of epicrisis as timeline detail
                    }
                });
                if (secTimeline) secTimeline.hidden = false;
            }

            // Stash combined markdown for Copy button — mirrors what is rendered,
            // not the full epicrisis history (that belongs to the Epicrisis tab).
            const patientMarkdown = await generatePatientMarkdown(patientData, latestDx);

            // Raw admission narrative bodies (no markdown header wrapping) —
            // fed to the AI tab's "narrative" field as-is. This is the one
            // piece HippoBridge has no further structure for (a single
            // free-text epicrisis/checkin field), so it still needs
            // server-side segmentation; everything else below (imaging) is
            // already known-typed and skips that guessing entirely.
            const narrativeParts = [];

            function admissionMarkdown(label, enc, isActive) {
                const start = enc.start ? formatDate(enc.start) : '';
                const end   = enc.end   ? formatDate(enc.end)   : '';
                const ms    = (enc.start && enc.end)
                    ? new Date(enc.end) - new Date(enc.start) : 0;
                const nights = ms > 0 ? Math.round(ms / 86400000) : 0;
                const period = isActive
                    ? `${start} → present (ongoing)`
                    : `${start} → ${end}${nights ? ` (${nights} ${nights === 1 ? 'night' : 'nights'})` : ''}`;
                const body = isActive
                    ? buildCheckinText(enc)
                    : extractEpicrisisText(enc).trim();
                if (!body) return ''; // no real content — omit the section entirely
                // rather than emit a header+date shell with nothing behind it:
                // a bare heading still reads as "populated" to callers that
                // just check for a non-empty string (e.g. getPatientClinicalText),
                // and a model handed only a header/date will confidently
                // fabricate a whole clinical scenario to fill the gap.
                narrativeParts.push(body);
                return `## ${label}\n\n_${period}_\n\n${body}\n\n`;
            }

            // primaryAdmissionMd/secondaryAdmissionMd are kept separate (rather
            // than one combined string) so the budgeted clinicalMarkdown below
            // can drop the lower-priority secondary block on its own; admissionsMd
            // (both concatenated) still feeds the full, unbudgeted Report tab display.
            let primaryAdmissionMd = '', secondaryAdmissionMd = '';
            if (activeAdm) {
                primaryAdmissionMd = admissionMarkdown('Current Admission', activeAdm.enc, true);
                const sparse = buildCheckinText(activeAdm.enc).length < SPARSE_THRESHOLD;
                if (sparse && lastDischarge)
                    secondaryAdmissionMd = admissionMarkdown('Last Admission', lastDischarge.enc, false);
            } else if (lastDischarge) {
                primaryAdmissionMd = admissionMarkdown('Last Admission', lastDischarge.enc, false);
            }
            const admissionsMd = primaryAdmissionMd + secondaryAdmissionMd;

            // One block per reported entry (most-recent first, same order as
            // `entries`) — kept separate, rather than one joined string, so the
            // budgeted clinicalMarkdown below can drop the oldest ones first;
            // imagingMd (all of them joined) still feeds the full, unbudgeted
            // Report tab display.
            const imagingBlocks = [];
            entries.forEach((sr, idx) => {
                if (!reports[idx]) return; // indication-only, no report to summarise
                const mod  = sr.type || '';
                const desc = sr.type_display || MODALITY_INFO[mod]?.label || mod;
                const date = sr.date_time ? formatDate(sr.date_time) : '';
                const code = sr.id || '';
                imagingBlocks.push(`### ${desc}  ·  ${date}${code ? '  #' + code : ''}\n\n${reports[idx]}\n\n`);
            });
            const imagingMd = imagingBlocks.length ? '## Recent Imaging\n\n' + imagingBlocks.join('') : '';

            // ── Hospitalisation timeline (mirrors the #reportTimeline rows above) ──
            function buildTimelineMarkdown(encs) {
                const lines = [];
                encs.forEach(item => {
                    const enc   = item.enc;
                    const start = enc.start ? formatDate(enc.start) : '';
                    const end   = enc.end   ? formatDate(enc.end)   : '';
                    if (!start && !end) return;
                    const rawDx = extractDiagnosisText(enc) || '';
                    const dx    = rawDx === '-' ? '' : rawDx;
                    const service = enc.service || enc.wards?.slice(-1)[0] || '';
                    const range = end ? `${start}→${end}` : start;
                    const label = [service, dx].filter(Boolean).join(' — ');
                    lines.push(`- **${range}**${label ? ' — ' + label : ''}`);
                });
                if (!lines.length) return '';
                return '## Hospitalization Timeline\n\n' + lines.join('\n') + '\n\n';
            }
            const timelineMd = buildTimelineMarkdown(encounters);

            const combined = patientMarkdown + admissionsMd + labsMd + imagingMd + timelineMd;
            if (markdownStore) markdownStore.dataset.markdown = combined;

            // Structured payload for the AI tab: imaging reports are already
            // known-typed here (reports[idx], fetched per-study from their own
            // API endpoint) — send them as-is, no re-guessing. The admission
            // narrative(s) are HippoBridge's one remaining free-text blob with
            // no further structure, sent separately for server-side segmentation.
            if (elements.patientReportBlocks) {
                const typedBlocks = entries
                    .map((entry, idx) => ({ hint_type: 'imaging', text: reports[idx] }))
                    .filter(b => b.text);
                elements.patientReportBlocks.dataset.blocks = JSON.stringify({
                    typed_blocks: typedBlocks,
                    narrative: narrativeParts.join('\n\n'),
                });
                // Priority order (lower = kept first when the text is over
                // budget): most-recent imaging, then the primary admission
                // narrative, then the 2nd-most-recent imaging, then labs, then
                // the remaining older imaging, then the secondary/sparse
                // admission block. See fitClinicalTextToBudget above.
                const imagingCandidates = imagingBlocks.map((text, idx) => ({
                    text: (idx === 0 ? '## Recent Imaging\n\n' : '') + text,
                    priority: idx === 0 ? 0 : idx === 1 ? 2 : 4 + (idx - 2),
                }));
                const clinicalCandidates = [
                    { text: primaryAdmissionMd, priority: 1 },
                    { text: secondaryAdmissionMd, priority: 7 },
                    { text: labsMd, priority: 3 },
                    ...imagingCandidates,
                ];
                elements.patientReportBlocks.dataset.clinicalMarkdown =
                    patientContextHeader(patientData, latestDx) +
                    fitClinicalTextToBudget(clinicalCandidates, CLINICAL_TEXT_CHAR_BUDGET);
            }

            if (reportCard) reportCard.hidden = false;
            log('Patient report displayed successfully');

        } catch (error) {
            console.error('Error displaying patient report:', error);
            showToast('Failed to generate patient report', 'error');
        }
    }
    
    async function generatePatientMarkdown(patientData, primaryDiagnosis) {
        log('Generating patient report markdown');
        const markdown = `# PATIENT CLINICAL REPORT\n\n` + patientContextHeader(patientData, primaryDiagnosis);
        log('Patient report markdown generated successfully');
        return markdown;
    }
    
    // Helper function to fetch encounter data for a checkout ID
    async function fetchEncounterDataForCheckout(checkoutId) {
        // check cache first
        if (cache.encounters[checkoutId]) {
            return cache.encounters[checkoutId];
        }

        const response = await apiFetch(`/api/checkout/${checkoutId}`);

        // 404 means this checkout simply isn't viewable via this scrape path
        // (e.g. superseded record) — a normal empty state, not a failure.
        if (response.status === 404) return null;
        if (!response.ok) {
            console.error(`Error fetching encounter data for checkout ${checkoutId}:`, response.status);
            throw new Error(`HTTP ${response.status}`);
        }

        const encounterData = (await response.json()).encounter || null;
        if (!encounterData) return null;
        cachePut(cache.encounters, checkoutId, encounterData);
        log(`Encounter data fetched successfully for checkout ${checkoutId}:`, encounterData);
        return encounterData;
    }

    // Helper function to fetch encounter data for a checkin ID (active admission, not yet discharged)
    async function fetchEncounterDataForCheckin(checkinId) {
        if (cache.encounters[checkinId]) {
            return cache.encounters[checkinId];
        }
        const response = await apiFetch(`/api/checkin/${checkinId}`);
        // 404 means this checkin simply isn't viewable via this scrape path
        // (e.g. superseded record) — a normal empty state, not a failure.
        if (response.status === 404) return null;
        if (!response.ok) {
            console.error(`Error fetching encounter data for checkin ${checkinId}:`, response.status);
            throw new Error(`HTTP ${response.status}`);
        }
        const encounterData = (await response.json()).encounter || null;
        if (!encounterData) return null;
        cachePut(cache.encounters, checkinId, encounterData);
        log(`Encounter data fetched successfully for checkin ${checkinId}:`, encounterData);
        return encounterData;
    }

    
    // ISO timestamp → short relative time ("just now", "2 h ago", "yesterday")
    function relativeTime(iso) {
        if (!iso) return '';
        const then = new Date(iso);
        if (isNaN(then)) return '';
        const s = Math.floor((Date.now() - then.getTime()) / 1000);
        if (s < 60) return 'just now';
        const m = Math.floor(s / 60);
        if (m < 60) return `${m} min ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `${h} h ago`;
        const d = Math.floor(h / 24);
        if (d === 1) return 'yesterday';
        if (d < 30) return `${d} days ago`;
        return iso.split('T')[0];
    }

    function loadRecentSearches() {
        if (!elements.recentSearchesList) return;
        const recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        elements.recentSearchesList.innerHTML = '';

        const hasItems = recentSearches.length > 0;
        if (elements.recentEmpty)   elements.recentEmpty.hidden = hasItems;
        if (elements.clearRecentBtn) elements.clearRecentBtn.hidden = !hasItems;

        const typeIcons = { cnp: 'fa-id-card', partial_cnp: 'fa-search', code: 'fa-barcode', name: 'fa-user', unknown: 'fa-question' };
        const tmpl = document.getElementById('recent-item-template');

        recentSearches.forEach(search => {
            const searchTerm = typeof search === 'string' ? search : search.term;
            const patientName = typeof search === 'object' ? search.patientName : null;
            const patientId = typeof search === 'object' ? search.patientId : null;
            const timestamp = typeof search === 'object' ? search.timestamp : null;
            const type = typeof search === 'object' ? search.type : 'unknown';

            const li = tmpl.content.cloneNode(true).querySelector('.recent-item');
            li.querySelector('i').className = `fas ${typeIcons[type] || 'fa-question'}`;

            const when = relativeTime(timestamp);
            li.querySelector('.recent-primary').textContent = patientName || searchTerm;
            li.querySelector('.recent-secondary').textContent = patientName
                ? [searchTerm, when].filter(Boolean).join(' · ')
                : when;

            const loadBtn = li.querySelector('.recent-load');
            loadBtn.title = `Search: ${searchTerm}`;
            loadBtn.setAttribute('aria-label', `Search ${patientName || searchTerm}`);
            loadBtn.addEventListener('click', () => {
                // Prefer the resolved patient ID — direct fetch, no picker overlay
                elements.cnpInput.value = patientId || searchTerm;
                elements.form.dispatchEvent(new Event('submit'));
            });

            elements.recentSearchesList.appendChild(li);
        });
    }

    function removeRecentSearch(searchTerm) {
        const recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        const filtered = recentSearches.filter(s => (typeof s === 'string' ? s : s.term) !== searchTerm);
        localStorage.setItem('recentSearches', JSON.stringify(filtered));
        loadRecentSearches();
    }

    function clearRecentSearches() {
        localStorage.removeItem('recentSearches');
        loadRecentSearches();
    }

    // Full-text search over epicrisis/imaging report text already indexed by
    // the server (GET /api/search/text — see search.py). Scoped to
    // patients already viewed through this HippoBridge instance, not a
    // Hipocrate-wide search (Hipocrate has no such API). Set once the server
    // reports the index isn't configured, so we stop calling on every keystroke.
    let clinicalSearchDisabledKnown = false;

    async function runClinicalSearch() {
        const query = elements.clinicalSearchInput?.value.trim() || '';
        if (elements.clinicalSearchResults) elements.clinicalSearchResults.innerHTML = '';
        if (elements.clinicalSearchEmpty) elements.clinicalSearchEmpty.hidden = true;
        if (!query || clinicalSearchDisabledKnown) return;

        let data;
        try {
            const resp = await apiFetch(`/api/search/text?q=${encodeURIComponent(query)}`);
            data = await resp.json();
        } catch (err) {
            log('Clinical text search failed (silent):', err);
            return;
        }

        if (!data.enabled) {
            clinicalSearchDisabledKnown = true;
            if (elements.clinicalSearchDisabled) elements.clinicalSearchDisabled.hidden = false;
            return;
        }

        const results = data.results || [];
        if (results.length === 0) {
            if (elements.clinicalSearchEmpty) elements.clinicalSearchEmpty.hidden = false;
            return;
        }
        renderClinicalSearchResults(results);
    }

    const CLINICAL_SEARCH_KIND_ICONS = { epicrisis: 'fa-file-medical', imaging: 'fa-x-ray' };

    function renderClinicalSearchResults(results) {
        const tmpl = document.getElementById('clinical-search-result-template');
        results.forEach(r => {
            const li = tmpl.content.cloneNode(true).querySelector('.recent-item');
            li.querySelector('.recent-avatar i').className =
                `fas ${CLINICAL_SEARCH_KIND_ICONS[r.kind] || 'fa-file'}`;
            li.querySelector('.recent-primary').textContent = r.patient_name || r.patient_cnp || 'Unknown patient';
            // Snippet's <mark> highlights come from the server's own FTS5
            // snippet() call (search.py), not user input.
            li.querySelector('.recent-snippet').innerHTML = r.snippet || '';

            const loadBtn = li.querySelector('.recent-load');
            const label = r.patient_name || r.patient_cnp || 'patient';
            loadBtn.title = `Open ${label}`;
            loadBtn.setAttribute('aria-label', `Open patient ${label}`);
            loadBtn.addEventListener('click', () => {
                elements.cnpInput.value = r.patient_cnp || r.patient_name;
                elements.form.dispatchEvent(new Event('submit'));
            });

            elements.clinicalSearchResults.appendChild(li);
        });
    }


    function addToRecentSearches(searchTerm, patientData = null) {
        let recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        
        // Create a rich search object with more details
        const searchItem = {
            term: searchTerm,
            timestamp: new Date().toISOString(),
            patientId: patientData?.id || null,
            patientName: patientData ? formatPatientName(patientData) : null,
            type: identifySearchType(searchTerm)
        };
        
        // Remove if exact term already exists
        recentSearches = recentSearches.filter(search => search.term !== searchTerm);
        
        // Add to beginning
        recentSearches.unshift(searchItem);
        
        // Keep only last 10 searches
        recentSearches = recentSearches.slice(0, 10);
        
        localStorage.setItem('recentSearches', JSON.stringify(recentSearches));
        loadRecentSearches();
    }
    
    function identifySearchType(searchTerm) {
        const v = validatePatientIdentifier(searchTerm);
        return v.isValid ? (v.type || 'unknown') : 'unknown';
    }
    
    function hideError() {
        elements.errorDiv.style.display = 'none';
    }
    
    function showToast(message, type = 'success', duration = 3000) {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }
        
        const toastTemplate = document.getElementById('toast-template');
        const toast = toastTemplate.content.cloneNode(true).querySelector('.toast');
        toast.className = `toast toast-${type}`;

        const iconMap = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };
        toast.querySelector('i').className = `fas ${iconMap[type] || 'fa-check-circle'}`;
        toast.querySelector('.toast-message').textContent = message;
        
        // Add toast to container
        toastContainer.appendChild(toast);
        
        // Auto-remove toast after duration
        const removeToast = () => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        };
        
        // Support for persistent toasts (duration = 0)
        if (duration > 0) {
            setTimeout(removeToast, duration);
        }
        
        // Allow manual dismissal by clicking
        toast.addEventListener('click', removeToast);
        
        return toast;
    }
    
    // Enhanced error handling with better user feedback
    function showError(message, details = null) {
        console.error('Application error:', message);
        
        // Show user-friendly error message
        elements.errorDiv.textContent = message;
        elements.errorDiv.style.display = 'block';
        
        // Show detailed error in console if provided
        if (details) {
            console.error('Error details:', details);
        }
        
        // Show toast notification
        showToast(message, 'error', 5000);
        
        hideLoading();
    }
    
    function showLoading(title = 'Loading patient data…') {
        elements.loadingOverlay.style.display = 'flex';
        if (elements.loadingSpinner) elements.loadingSpinner.hidden = false;
        if (elements.loadingError) elements.loadingError.hidden = true;
        elements.analyzeBtn.disabled = true;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading…';
        const titleEl = document.getElementById('loadingTitle');
        if (titleEl) titleEl.textContent = title;
        if (elements.loadingStep) elements.loadingStep.textContent = '';
    }

    function setLoadingStep(text) {
        if (elements.loadingStep) elements.loadingStep.textContent = text;
    }
    
    // Markdown to HTML conversion now uses marked.js library
    // marked.parse(markdownText) converts markdown to HTML

    // Hipocrate's Rezultate.asp save strips HTML tags entirely unless they're
    // wrapped in a block element, and its pre-validation cerere.asp preview
    // shows any surviving <p> literally. Sending plain text with a blank line
    // between sentences avoids both: no tags to strip or leak, and Hipocrate's
    // own storage/preview appears to turn real newlines into visible breaks.

    function displayPatientData(patientData) {
        log('Displaying patient data:', patientData);

        const name = formatPatientName(patientData);
        if (name) setPageTitle(name);

        // Enhanced patient information display with better formatting
        displayPatientBasicInfo(patientData);
        
        // Extract and display medical statistics
        const stats = extractMedicalStats(patientData);
        log('Extracted medical stats:', stats);
        displayMedicalStats(stats);
        
        if (elements.imagingGrid) elements.imagingGrid.innerHTML = '';
        if (elements.labGrid) elements.labGrid.innerHTML = '';

        // Hospitalisation history loads lazily; don't block the profile render
        loadHospitalisationHistory(patientData);

        log('Patient data display completed');
    }

    async function loadHospitalisationHistory(patientData) {
        if (!elements.historyList) return;
        elements.historyList.innerHTML = '';
        if (elements.historyEmpty) elements.historyEmpty.hidden = true;

        const checkoutIds = extractCheckoutIds(patientData);
        const checkoutIdSet = new Set(checkoutIds);
        // Same id can appear in both lists once discharged — checkout wins, so only
        // fetch as "checkin" the ids that are still active (not yet checked out).
        const checkinIds = extractCheckinIds(patientData).filter(id => !checkoutIdSet.has(id));
        const presentationIds = extractPresentationIds(patientData);

        if (checkoutIds.length === 0 && checkinIds.length === 0 && presentationIds.length === 0) {
            if (elements.historyEmpty) elements.historyEmpty.hidden = false;
            return;
        }

        if (elements.historyLoading) elements.historyLoading.hidden = false;
        try {
            // A null result means either "not found" (404 — a normal, silent
            // outcome; see fetchEncounterDataForCheckout etc.) or a genuine
            // fetch failure. Only the latter should count toward the warning
            // toast below, so track it explicitly instead of inferring it
            // from missing results.
            let failedCount = 0;
            const [encounters, activeEncounters, presentations] = await Promise.all([
                limitedMap(checkoutIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchEncounterDataForCheckout(id); } catch (_) { failedCount++; return null; } }),
                limitedMap(checkinIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchEncounterDataForCheckin(id); } catch (_) { failedCount++; return null; } }),
                limitedMap(presentationIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchPresentation(id); } catch (_) { failedCount++; return null; } })
            ]);

            if (failedCount > 0) {
                showToast(`Failed to load ${failedCount} history record${failedCount > 1 ? 's' : ''}`, 'warning');
            }

            // Build a unified list with type tags
            const encItems = encounters.filter(Boolean).map(enc => ({
                type: 'inpatient',
                enc,
                sortKey: enc.end || enc.start || '',
                start: enc.start || '',
                end: enc.end || '',
                label: extractDiagnosisText(enc) || 'No diagnosis recorded',
                section: enc.wards?.[0] || '',
                medic: enc.medic || '',
                extra: '',
            }));

            // Active admissions (checked in, not yet discharged) — no end date yet.
            const activeItems = activeEncounters.filter(Boolean).map(enc => ({
                type: 'inpatient',
                enc,
                sortKey: enc.start || '',
                start: enc.start || '',
                end: '',
                label: extractDiagnosisText(enc) || 'No diagnosis recorded',
                section: enc.wards?.[0] || '',
                medic: enc.medic || '',
                extra: '',
            }));

            const presItems = presentations.filter(Boolean).map(enc => {
                const start = enc.start || '';
                const section = enc.wards?.[0] || '';
                const reason = enc.reason || '';
                const notes = enc.notes || [];
                const decision = notes[0] || '';
                const consultType = notes[1] || '';
                const label = reason || consultType || 'Outpatient visit';
                return {
                    type: 'outpatient',
                    enc,
                    sortKey: start,
                    start: start ? formatDate(start) : '',
                    end: '',
                    label,
                    section,
                    medic: enc.medic || '',
                    extra: decision,
                };
            });

            const items = [...encItems, ...activeItems, ...presItems]
                .sort((a, b) => b.sortKey.localeCompare(a.sortKey));

            if (items.length === 0) {
                if (elements.historyEmpty) elements.historyEmpty.hidden = false;
                return;
            }

            // Populate diagnosis badge from most recent inpatient discharge if not already set
            if (elements.patientDiagnosis && elements.patientDiagnosis.hidden) {
                const latest = items.find(i => i.type === 'inpatient');
                const latestDx = latest && extractDiagnosisText(latest.enc);
                if (latestDx) {
                    elements.patientDiagnosis.textContent = latestDx;
                    elements.patientDiagnosis.hidden = false;
                }
            }

            const tmpl = document.getElementById('history-item-template');
            items.forEach(({ type, enc, start, end, label, section, medic, extra }, idx) => {
                const li = tmpl.content.cloneNode(true).querySelector('.history-item');
                li.dataset.type = type;

                if (type === 'inpatient') {
                    const period = [start && formatDate(start), end && formatDate(end)]
                        .filter(Boolean).join(' → ');
                    li.querySelector('.history-period').textContent = period || 'Unknown period';

                    const nightsEl = li.querySelector('.history-nights');
                    if (nightsEl && start && end) {
                        const ms = new Date(end) - new Date(start);
                        const nights = Math.round(ms / 86400000);
                        if (nights > 0) nightsEl.textContent = `${nights}d`;
                        else nightsEl.hidden = true;
                    } else if (nightsEl) nightsEl.hidden = true;

                    li.querySelector('.history-load').addEventListener('click', () => switchTab('epicrisis'));
                } else {
                    // Outpatient presentation: show date + section
                    const period = [start, section].filter(Boolean).join(' · ');
                    li.querySelector('.history-period').textContent = period || 'Unknown date';

                    const nightsEl = li.querySelector('.history-nights');
                    if (nightsEl) nightsEl.hidden = true;

                    const typeEl = li.querySelector('.history-type');
                    if (typeEl) { typeEl.textContent = extra || 'Outpatient'; typeEl.hidden = false; }

                    li.querySelector('.history-load').addEventListener('click', () => switchTab('imaging'));
                }

                li.querySelector('.history-diagnosis').textContent = label;

                if (idx === items.length - 1) {
                    const line = li.querySelector('.history-line');
                    if (line) line.hidden = true;
                }

                elements.historyList.appendChild(li);
            });
        } catch (err) {
            log('Failed to load history:', err);
            if (elements.historyEmpty) elements.historyEmpty.hidden = false;
        } finally {
            if (elements.historyLoading) elements.historyLoading.hidden = true;
        }
    }
    
    // Enhanced patient basic info display
    function displayPatientBasicInfo(patientData) {
        log('Displaying patient basic info:', patientData);
        
        // Patient Name
        const name = formatPatientName(patientData);
        if (elements.patientName) elements.patientName.textContent = name;
        if (elements.patientNameInfo) elements.patientNameInfo.textContent = name || '—';
        log('Patient name set to:', name);

        // Show who is loaded in the nav: "FAMILY G." instead of "Patient Profile"
        if (elements.navPatientLabel) {
            const family = patientData.family_name || '';
            const givenInitial = patientData.given_name ? ` ${patientData.given_name.trim()[0]}.` : '';
            elements.navPatientLabel.textContent = family ? `${family}${givenInitial}` : 'Patient Profile';
        }
        
        // Meta badges: ID · gender + age · diagnosis
        const age = calculateAge(patientData.birth_date);
        if (elements.patientAgeInfo) elements.patientAgeInfo.textContent = age !== 'N/A' ? age : '—';
        if (elements.patientId) {
            const pid = patientData.id || '';
            const patHippoUrl = patientHipocrateUrl(patientData);
            elements.patientId.innerHTML = '';
            if (pid && patHippoUrl) {
                const a = document.createElement('a');
                a.href = patHippoUrl;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.textContent = `ID: ${pid}`;
                elements.patientId.appendChild(a);
            } else if (pid) {
                elements.patientId.textContent = `ID: ${pid}`;
            }
        }

        // Gender icon + age in one badge
        const genderIcon = patientData.sex === 'female' ? 'fa-venus' : patientData.sex === 'male' ? 'fa-mars' : null;
        const genderLabel = formatGender(patientData.sex);
        const ageLabel = age !== 'N/A' ? age : null;
        if (elements.patientGender) {
            elements.patientGender.innerHTML = '';
            if (genderIcon) {
                const icon = document.createElement('i');
                icon.className = `fas ${genderIcon}`;
                icon.style.fontSize = '11px';
                elements.patientGender.appendChild(icon);
                elements.patientGender.appendChild(document.createTextNode(` ${genderLabel}${ageLabel ? ' · ' + ageLabel : ''}`));
            } else {
                elements.patientGender.textContent = [genderLabel, ageLabel].filter(Boolean).join(' · ');
            }
        }

        log('Age set to:', age);
        
        // Personal info fields
        const cnp = patientData.cnp || null;
        // Presumed valid unless the backend explicitly flags it invalid
        // (checksum/date/county-code failure — see extractors.py parse_cnp).
        const cnpValid = patientData.cnp_valid !== false;
        if (elements.patientCnp) {
            elements.patientCnp.textContent = cnp || '—';
            elements.patientCnp.classList.toggle('cnp-invalid', !!cnp && !cnpValid);
            elements.patientCnp.title = (cnp && !cnpValid) ? 'This CNP failed validation (checksum/date/county code) — verify with the patient record' : '';
        }
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = formatBirthDate(patientData.birth_date) || '—';

        const contactInfo = { phone: formatPhoneNumber(patientData.phone), email: patientData.email || null };
        if (elements.patientPhone) elements.patientPhone.textContent = contactInfo.phone || '—';
        if (elements.patientEmail) elements.patientEmail.textContent = contactInfo.email || '—';
        if (elements.patientAddress) {
            const text = patientData.address || '';
            const district = patientData.county || '';
            const display = district && !text.includes(district) ? `${text}, ${district}` : text;
            elements.patientAddress.textContent = display || '—';
        }
        log('CNP:', cnp, 'Phone:', contactInfo.phone, 'Email:', contactInfo.email);

        // QR codes
        const lastName  = patientData.family_name || '';
        const firstName = (patientData.given_name || '').split(/\s+/)[0] || '';
        const birthDate = patientData.birth_date || '';
        renderQr(elements.qrLastName,  lastName);
        renderQr(elements.qrFirstName, firstName);
        renderQr(elements.qrCnp,       cnp || '');
        renderQr(elements.qrBirthDate, birthDate);
        if (elements.qrLabelLastName)  elements.qrLabelLastName.textContent  = lastName;
        if (elements.qrLabelFirstName) elements.qrLabelFirstName.textContent = firstName;
        if (elements.qrLabelCnp)       elements.qrLabelCnp.textContent       = cnp || '';
        if (elements.qrLabelBirthDate) elements.qrLabelBirthDate.textContent = birthDate;
        if (elements.qrPanel) elements.qrPanel.hidden = !(lastName || firstName || cnp);
    }
    
    // Enhanced name formatting
    function toTitleCase(str) {
        return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
    }

    function renderQr(canvas, text) {
        if (!canvas || !text) return;
        canvas.dataset.qrText = text;
        const qr = qrcode(0, 'L');
        qr.addData(text);
        qr.make();
        const modules = qr.getModuleCount();
        const quiet   = 4;
        const cell    = 5;
        const size    = (modules + quiet * 2) * cell;
        canvas.width  = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        const dark = document.documentElement.getAttribute('data-theme') === 'dark';
        ctx.fillStyle = dark ? '#0e1626' : '#ffffff';
        ctx.fillRect(0, 0, size, size);
        ctx.fillStyle = dark ? '#8b93f8' : '#312e81';
        for (let r = 0; r < modules; r++) {
            for (let c = 0; c < modules; c++) {
                if (!qr.isDark(r, c)) continue;
                ctx.fillRect((c + quiet) * cell, (r + quiet) * cell, cell, cell);
            }
        }
    }

    // Patient record from /api/patient/{id} (or a single-match /api/patient?q=):
    // the `patient` object (name, family_name, given_name, cnp, cnp_valid, sex,
    // birth_date, phone, email, address, city, county, weight, height, …) plus
    // the encounter id lists flattened in. This is the shape every patientData
    // consumer below reads.
    function patientFromApi(d) {
        return {
            ...(d?.patient || {}),
            presentation_ids: d?.presentation || [],
            checkin_ids: d?.checkin || [],
            checkout_ids: d?.checkout || [],
        };
    }

    // Link to the patient's page in Hipocrate ('' until the base URL is known).
    function patientHipocrateUrl(p) {
        return hipocrateUrl && p?.id ? `${hipocrateUrl}/Pacient/edit.asp?id=${encodeURIComponent(p.id)}` : '';
    }

    function formatPatientName(p) {
        if (!p) return 'N/A';
        const family = p.family_name ? toTitleCase(p.family_name) : '';
        const given  = p.given_name  ? toTitleCase(p.given_name) : '';

        if (family && given) return `${family}, ${given}`;
        if (family) return family;
        if (given)  return given;
        return 'N/A';
    }

    // Initials only (e.g. "J.D.") — for headings prepended to text sent to
    // the LLM, so the model never sees the patient's full name.
    function formatPatientInitials(p) {
        if (!p) return 'N/A';
        const familyInitial = p.family_name ? p.family_name.trim()[0]?.toUpperCase() : '';
        const givenInitials = p.given_name
            ? p.given_name.split(/\s+/).map(g => g.trim()[0]?.toUpperCase()).filter(Boolean).join('.')
            : '';
        const parts = [givenInitials, familyInitial].filter(Boolean);
        return parts.length ? parts.join('.') + '.' : 'N/A';
    }

    // Shared "Initials | Age | Sex | Diagnosis" context line — no name/DOB/
    // CNP — prepended to every tab-level AI|Copy toolbar's copied Markdown
    // and AI input (Patient Report, Lab Trends, Imaging current episode,
    // Hospitalization, and the Profile "AI Summary"/pre-exam text they all
    // share via getPatientClinicalText()). `diagnosis` overrides the
    // page-wide #patientDiagnosis text when a caller already has a more
    // specific one on hand (e.g. the Report tab's own latestDx).
    function patientContextLine(patientData, diagnosis) {
        if (!patientData) return '';
        const initials = formatPatientInitials(patientData);
        const age = calculateAge(patientData.birth_date);
        const gender = formatGender(patientData.sex);
        const dx = diagnosis ?? elements.patientDiagnosis?.textContent?.trim();
        return [initials, age, gender, dx].filter(v => v && v !== 'N/A').join(' | ');
    }

    function patientContextHeader(patientData, diagnosis) {
        const line = patientContextLine(patientData, diagnosis);
        return line ? `${line}\n\n` : '';
    }

    // Enhanced gender formatting with icons
    function formatGender(gender) {
        if (!gender) return 'N/A';
        
        const genderMap = {
            'male': 'Male ♂',
            'female': 'Female ♀',
            'other': 'Other',
            'unknown': 'Unknown'
        };
        
        return genderMap[gender] || gender;
    }
    
    // Enhanced birth date formatting
    function formatBirthDate(birthDate) {
        if (!birthDate) return 'N/A';
        return formatDate(birthDate);
    }
    
    // Enhanced phone number formatting
    function formatPhoneNumber(phoneNumber) {
        if (!phoneNumber) return null;
        
        // Remove all non-digit characters
        const digits = phoneNumber.replace(/\D/g, '');
        
        // Format based on length
        if (digits.length === 10) {
            // Romanian phone number format
            return `0 ${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
        } else if (digits.length === 12 && digits.startsWith('40')) {
            // International format with country code
            return `+40 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
        }
        
        return phoneNumber;
    }
    
    // Medical statistics from the patient's encounter id lists
    function extractMedicalStats(patientData) {
        const checkoutIds = extractCheckoutIds(patientData);
        return {
            encounters: extractPresentationIds(patientData).length,
            admissions: extractCheckinIds(patientData).length,
            discharges: checkoutIds.length,
            checkoutIds,
        };
    }
    
    // Enhanced medical stats display
    function displayMedicalStats(stats) {
        log('Displaying medical stats:', stats);
        elements.presentationsCount.textContent = stats.encounters;
        elements.checkinsCount.textContent = stats.admissions;
        elements.checkoutsCount.textContent = stats.discharges;
        log('Stats displayed - Encounters:', stats.encounters, 'Admissions:', stats.admissions, 'Discharges:', stats.discharges);
        
        // Update reports count if element exists
        if (elements.imagingCount) elements.imagingCount.textContent = '?';
        if (elements.labCount) elements.labCount.textContent = '?';
    }
    
    
    function calculateAge(birthDate) {
        if (!birthDate) return 'N/A';
        const parts = String(birthDate).split('-').map(Number);
        if (parts.length < 2 || isNaN(parts[0])) return 'N/A';
        const [year, month, day = 1] = parts;
        const today = new Date();
        const todayY = today.getFullYear(), todayM = today.getMonth() + 1, todayD = today.getDate();

        let years = todayY - year;
        let months = todayM - month;
        let days = todayD - day;
        if (days < 0)   { months--; days += 30; }
        if (months < 0) { years--;  months += 12; }

        if (years >= 2)  return `${years} years`;
        if (years === 1) return months > 0 ? `1 year ${months} months` : '1 year';
        if (months >= 1) return `${months} month${months !== 1 ? 's' : ''}`;
        return `${Math.max(days, 0)} day${days !== 1 ? 's' : ''}`;
    }
    
    // Function to view imaging study
    async function viewImagingStudy(studyId, reportId) {
        try {
            const studyResponse = await apiFetch(`/api/study/${studyId}`);
            
            if (!studyResponse.ok) {
                const msg = studyResponse.status === 401
                    ? 'Authentication required. Please sign in again.'
                    : `Error loading imaging study ${studyId} (HTTP ${studyResponse.status})`;
                showToast(msg, 'error');
                return;
            }

            const studyData = await studyResponse.json();
            displayImagingStudyModal(studyData, studyId, reportId);

        } catch (err) {
            console.error('Error fetching imaging study:', err);
            showToast(`Error loading imaging study ${studyId}`, 'error');
        }
    }
    
    // Function to display imaging study in a modal
    function displayImagingStudyModal(studyData, studyId, reportId) {
        // Use template for modal
        const modalTemplate = document.getElementById('imaging-study-modal-template');
        const modal = modalTemplate.content.cloneNode(true).querySelector('dialog');
        modal.id = 'imagingStudyModal';
        
        modal.querySelector('.modal-title').textContent = `Imaging Study #${studyId}`;
        
        // Populate study information
        const studyInfo = modal.querySelector('.study-info');
        populateStudyInfo(studyInfo, studyData);
        
        // Populate series information
        const seriesList = modal.querySelector('.series-list');
        populateSeriesList(seriesList, studyData);
        
        // Set back to report link
        const backLink = modal.querySelector('.back-to-report');
        backLink.href = '#';
        backLink.querySelector('.back-report-id').textContent = `#${reportId}`;
        backLink.addEventListener('click', function(e) {
            e.preventDefault();
            modal.close();
        });
        
        // Add event listeners for closing the modal
        const closeButtons = modal.querySelectorAll('[data-close-modal], .close');
        closeButtons.forEach(button => {
            button.addEventListener('click', () => modal.close());
        });
        // Escape fires 'close' too — single removal path keeps the DOM clean
        modal.addEventListener('close', () => modal.remove());
        
        // Add modal to document and show
        document.body.appendChild(modal);
        modal.showModal();
    }
    
    function addStudyInfoRow(container, icon, label, value) {
        const tmpl = document.getElementById('study-info-row-template');
        const p = tmpl.content.cloneNode(true).querySelector('p');
        p.querySelector('i').className = `fas ${icon}`;
        p.querySelector('.row-label').textContent = `${label}:`;
        p.querySelector('.row-value').textContent = value;
        container.appendChild(p);
    }

    function populateStudyInfo(studyInfo, studyData) {
        const studies = studyData.studies || [];
        const first = studies[0] || {};
        const requester = studyData.checkin?.medic;
        if (studyData.request?.date_time)
            addStudyInfoRow(studyInfo, 'fa-calendar', 'Started', formatDateWithTime(studyData.request.date_time));
        if (first.type)
            addStudyInfoRow(studyInfo, 'fa-stethoscope', 'Modality', MODALITY_INFO[first.type]?.label || first.type);
        if (first.title)
            addStudyInfoRow(studyInfo, 'fa-file-medical', 'Description', first.title);
        if (first.validator || requester)
            addStudyInfoRow(studyInfo, 'fa-user-md', 'Performer', first.validator || requester);
        if (requester)
            addStudyInfoRow(studyInfo, 'fa-user-check', 'Referrer', requester);
        if (studyData.checkin?.diagnosis)
            addStudyInfoRow(studyInfo, 'fa-question-circle', 'Reason', studyData.checkin.diagnosis);
        if (studyData.request?.justification)
            addStudyInfoRow(studyInfo, 'fa-notes-medical', 'Justificare', studyData.request.justification);
        const reported = studies.find(st => st.result);
        if (reported)
            addStudyInfoRow(studyInfo, 'fa-sticky-note', 'Note', reported.result);
    }
    
    function populateSeriesList(seriesList, studyData) {
        const studies = studyData.studies || [];
        if (studies.length === 0) return;
        const tmpl = document.getElementById('series-item-template');
        studies.forEach((study, index) => {
            const li = tmpl.content.cloneNode(true).querySelector('li');
            li.querySelector('.series-label').textContent = `Series ${index + 1}:`;
            li.querySelector('.series-desc').textContent = study.title || 'N/A';
            const modalitySpan = li.querySelector('.series-modality');
            if (study.type) {
                modalitySpan.textContent = ` (Modality: ${MODALITY_INFO[study.type]?.label || study.type})`;
            }
            seriesList.appendChild(li);
        });
    }
    
    // Function to close imaging study modal
    function closeImagingStudyModal() {
        const modal = document.getElementById('imagingStudyModal');
        if (modal) {
            modal.close();
        }
    }
    
    // Make functions available globally
    window.viewImagingStudy = viewImagingStudy;
    window.closeImagingStudyModal = closeImagingStudyModal;
    
    // Populate a study grid (imaging or lab) from a pre-filtered entries array.
    // ctx: { grid, noData, eyebrow, eyebrowLabel, metaId, types }
    async function populateStudyGrid(entries, ctx) {
        const { grid, noData, eyebrow, eyebrowLabel, metaId, types, patientData, allDates } = ctx;
        const myGeneration = dataGeneration;

        if (entries.length === 0) {
            if (noData) noData.style.display = 'block';
            if (grid) grid.innerHTML = '';
            if (grid?.id === 'imagingGrid' && elements.imagingCount) elements.imagingCount.textContent = '0';
            if (grid?.id === 'labGrid' && elements.labCount) elements.labCount.textContent = '0';
            return;
        }

        if (noData) noData.style.display = 'none';
        if (grid) grid.innerHTML = '';

        if (eyebrow) eyebrow.textContent = eyebrowLabel;
        if (grid?.id === 'imagingGrid' && elements.imagingCount) elements.imagingCount.textContent = entries.length;
        if (grid?.id === 'labGrid' && elements.labCount) elements.labCount.textContent = entries.length;

        const countByType = {};
        for (const e of entries) {
            const t = e.type || 'unknown';
            countByType[t] = (countByType[t] || 0) + 1;
        }

        const metaEl = metaId ? document.getElementById(metaId) : null;
        if (metaEl) {
            const parts = types.filter(t => countByType[t]).map(t => `${countByType[t]} ${MODALITY_INFO[t]?.label || t}`);
            metaEl.textContent = parts.join(', ') || `${entries.length} studies`;
        }

        // Update chip counts for this grid's chip container
        const chipsId = grid?.id === 'imagingGrid' ? 'imagingChips' : 'labChips';
        document.querySelectorAll(`#${chipsId} .chip`).forEach(chip => {
            const f = chip.dataset.filter;
            const count = f === 'all' ? entries.length : (countByType[f] || 0);
            const label = chip.textContent.replace(/\s*\(\d+\)$/, '');
            chip.textContent = `${label} (${count})`;
            if (f !== 'all' && count === 0) { chip.style.opacity = '0.4'; chip.disabled = true; }
            else { chip.style.opacity = ''; chip.disabled = false; }
        });

        // Split into Current Episode / Prior Episodes using the shared
        // episode boundary. entries[] arrives already sorted most-recent-
        // first by the backend, so each partition stays in that order.
        let currentEntries = entries, historicalEntries = [];
        let showDividers = false;
        if (patientData) {
            const { boundaryDate } = await getEpisodeBoundary(patientData, allDates || []);
            if (myGeneration !== dataGeneration) return; // patient changed while awaiting
            if (boundaryDate) {
                showDividers = true;
                currentEntries = entries.filter(e => (e.date_time || '') >= boundaryDate);
                historicalEntries = entries.filter(e => (e.date_time || '') < boundaryDate);
            }
        }

        // Create cards immediately; lazily load report content as cards scroll into view
        const cards = [];
        const appendSection = (label, list) => {
            if (!list.length) return;
            if (showDividers) {
                // Current Episode's imaging heading additionally gets an AI |
                // Copy toolbar (mirroring Lab Trends) when there's more than
                // one study to compare — a single study already has its own
                // per-card AI button.
                const wantsEpisodeToolbar = label === 'Current Episode' && grid.id === 'imagingGrid' && list.length > 1;
                if (wantsEpisodeToolbar) {
                    grid.appendChild(buildImagingEpisodeHeader(list, patientData));
                } else {
                    const heading = document.createElement('h3');
                    heading.className = 'episode-divider';
                    heading.textContent = label;
                    grid.appendChild(heading);
                }
            }
            for (const sr of list) {
                const type = sr.type || 'unknown';
                const text = sr.type_display || 'analysis';
                const card = createAnalysisCard(sr, type, text);
                grid.appendChild(card);
                cards.push(card);
            }
        };
        appendSection('Current Episode', currentEntries);
        appendSection('Prior Episodes', historicalEntries);

        const observer = new IntersectionObserver((observed, obs) => {
            for (const entry of observed) {
                if (entry.isIntersecting) {
                    obs.unobserve(entry.target);
                    fetchAndFillReport(entry.target);
                }
            }
        }, { rootMargin: '120px' });

        for (const card of cards) observer.observe(card);
    }

    // ── Lab result table ────────────────────────────────────────────────────

    function buildLabTable(forms) {
        // Group by section
        const sections = {};
        for (const form of forms) {
            const sec = form.section || '';
            if (!sections[sec]) sections[sec] = [];
            sections[sec].push(form);
        }
        const wrap = document.createElement('div');
        wrap.className = 'lab-result-wrap';
        for (const [sec, entries] of Object.entries(sections)) {
            if (sec) {
                const heading = document.createElement('p');
                heading.className = 'lab-section-heading';
                heading.textContent = sec;
                wrap.appendChild(heading);
            }
            const table = document.createElement('table');
            table.className = 'lab-result-table';
            const tbody = table.createTBody();
            for (const form of entries) {
                const row = tbody.insertRow();
                const tdName = row.insertCell();
                tdName.className = 'lab-name';
                tdName.textContent = form.title || '';
                const tdVal = row.insertCell();
                tdVal.className = 'lab-value' + (form.flag === 'H' ? ' lab-high' : form.flag === 'L' ? ' lab-low' : '');
                tdVal.textContent = form.data || '';
                const tdRef = row.insertCell();
                tdRef.className = 'lab-ref';
                tdRef.textContent = form.reference || '';
                if (form.flag && form.flag !== 'N') {
                    tdVal.appendChild(document.createTextNode(' '));
                    const badge = document.createElement('span');
                    badge.className = 'lab-flag lab-flag-' + form.flag.toLowerCase();
                    badge.textContent = form.flag;
                    tdVal.appendChild(badge);
                }
            }
            wrap.appendChild(table);
        }
        return wrap;
    }

    // Build a concise Markdown table (Test | Value | Reference) from the same
    // report forms buildLabTable renders, grouped by section. The
    // reference cell already carries the measurement unit.
    function buildLabMarkdown(forms) {
        const cell = s => (s || '').replace(/\s*\n+\s*/g, ' ').replace(/\|/g, '\\|').trim();
        const sections = {};
        for (const form of forms) {
            const sec = form.section || '';
            (sections[sec] ||= []).push(form);
        }
        const blocks = [];
        for (const [sec, entries] of Object.entries(sections)) {
            const lines = [];
            if (sec) lines.push(`**${cell(sec)}**`, '');
            lines.push('| Test | Value | Reference |', '| --- | --- | --- |');
            for (const form of entries) {
                lines.push(`| ${cell(form.title)} | ${cell(form.data)} | ${cell(form.reference)} |`);
            }
            blocks.push(lines.join('\n'));
        }
        return blocks.join('\n\n');
    }

    // ── Lab Trends ──────────────────────────────────────────────────────────

    function sparkline(measurements, low, high, width, height) {
        width  = width  || 80;
        height = height || 22;
        const vals = measurements.map(m => m.v).filter(v => v !== null && v !== undefined);
        if (vals.length < 2) return '';
        const lo  = Math.min(...vals, low  !== null ? low  : Infinity);
        const hi  = Math.max(...vals, high !== null ? high : -Infinity);
        const span = hi - lo || 1;
        const pts = measurements
            .filter(m => m.v !== null && m.v !== undefined)
            .map((m, i, arr) => {
                const x = arr.length === 1 ? width / 2 : (i / (arr.length - 1)) * width;
                const y = height - ((m.v - lo) / span) * (height - 2) - 1;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(' ');
        // Reference band
        let band = '';
        if (low !== null && high !== null) {
            const y1 = height - ((high - lo) / span) * (height - 2) - 1;
            const y2 = height - ((low  - lo) / span) * (height - 2) - 1;
            band = `<rect x="0" y="${y1.toFixed(1)}" width="${width}" height="${(y2 - y1).toFixed(1)}" class="trend-band"/>`;
        }
        return `<svg class="trend-sparkline" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true">${band}<polyline points="${pts}" fill="none" class="trend-line"/></svg>`;
    }

    function renderTrends(observations) {
        if (!elements.trendsContainer || !elements.trendsSection) return;

        // Group by section+analyte name — the section prefix matters because the
        // same analyte name can appear under different sections (e.g. "Glucoza"
        // in blood chemistry vs. urine); keying by name alone would silently
        // merge their measurements into one row.
        const byAnalyte = {};
        for (const obs of observations) {
            const name = obs.analyte;
            if (!name) continue;
            const section = obs.section || '';
            const key = `${section}::${name}`;
            if (!byAnalyte[key]) {
                byAnalyte[key] = {
                    name,
                    section,
                    unit: obs.unit || '',
                    low:  obs.low  ?? null,
                    high: obs.high ?? null,
                    ref:  obs.reference || '',
                    measurements: [],
                };
            }
            byAnalyte[key].measurements.push({
                date: obs.date || '',
                v:    obs.value ?? null,
                text: obs.value_text || null,
                flag: obs.flag || null,
            });
        }

        // Only analytes with at least one numeric value
        const analytes = Object.values(byAnalyte).filter(a =>
            a.measurements.some(m => m.v !== null)
        );
        if (!analytes.length) return;

        // Sort measurements chronologically per analyte
        for (const a of analytes) {
            a.measurements.sort((x, y) => x.date.localeCompare(y.date));
        }

        // Section, then analyte name within each section — mirrors the Recent
        // Labs report section's grouping so the same disambiguation applies here.
        analytes.sort((a, b) => a.section.localeCompare(b.section) || a.name.localeCompare(b.name));

        // All unique dates (oldest first) for column headers
        const allDates = [...new Set(observations.map(o => o.date?.slice(0, 10)).filter(Boolean))].sort();
        const colDates = allDates.slice(-5);  // cap table at 5 most recent dates

        // Build one table per section — mirrors the Recent Labs report section's
        // section-then-analyte grouping (same reason: disambiguates analytes that
        // share a name across sections, e.g. "Glucoza" in blood vs. urine).
        function buildTrendsTable(sectionAnalytes) {
        const table = document.createElement('table');
        table.className = 'trends-table';

        // Column widths (fixed layout — ensures header/data cells share the same column width)
        const colgroup = document.createElement('colgroup');
        const mkCol = w => { const c = document.createElement('col'); c.style.width = w; return c; };
        colgroup.appendChild(mkCol('220px'));
        colDates.forEach(() => colgroup.appendChild(mkCol('110px')));
        colgroup.appendChild(mkCol('100px'));
        table.appendChild(colgroup);

        // Header row
        const thead = table.createTHead();
        const hrow  = thead.insertRow();
        const th0 = document.createElement('th');
        th0.textContent = 'Analyte';
        hrow.appendChild(th0);
        for (const d of colDates) {
            const th = document.createElement('th');
            th.textContent = d;
            th.className = 'trend-date-col';
            hrow.appendChild(th);
        }
        const thSpark = document.createElement('th');
        thSpark.textContent = 'Trend';
        thSpark.className = 'trend-spark-col';
        hrow.appendChild(thSpark);

        // Data rows
        const tbody = table.createTBody();
        for (const a of sectionAnalytes) {
            const row = tbody.insertRow();

            // Analyte name + unit + reference
            const tdName = row.insertCell();
            tdName.className = 'trend-name';
            const nameEl = document.createElement('span');
            const MAX_NAME = 48;
            if (a.name.length > MAX_NAME) {
                const cut = a.name.lastIndexOf(' ', MAX_NAME);
                nameEl.textContent = a.name.slice(0, cut > 0 ? cut : MAX_NAME) + '…';
                nameEl.title = a.name;
            } else {
                nameEl.textContent = a.name;
            }
            tdName.appendChild(nameEl);
            if (a.unit || a.ref) {
                const sub = document.createElement('span');
                sub.className = 'trend-meta';
                sub.textContent = [a.unit, a.ref ? `(${a.ref})` : ''].filter(Boolean).join(' ');
                tdName.appendChild(sub);
            }

            // Value columns — one per date
            const byDate = {};
            for (const m of a.measurements) byDate[m.date?.slice(0, 10) || ''] = m;

            for (const d of colDates) {
                const td  = row.insertCell();
                const m   = byDate[d];
                if (!m) { td.textContent = '–'; td.className = 'trend-empty'; continue; }
                td.textContent = m.v !== null ? ((Number.isInteger(m.v) ? m.v : parseFloat(m.v.toPrecision(4))) + (a.unit ? ' ' + a.unit : '')) : (m.text || '–');
                if (m.flag === 'H') td.className = 'trend-high';
                else if (m.flag === 'L') td.className = 'trend-low';
            }

            // Sparkline cell — restricted to the same colDates window
            const tdSpark = row.insertCell();
            tdSpark.className = 'trend-spark-col';
            const colSet = new Set(colDates);
            tdSpark.innerHTML = sparkline(a.measurements.filter(m => colSet.has(m.date?.slice(0, 10))), a.low, a.high);
        }
        return table;
        }

        elements.trendsContainer.innerHTML = '';
        let lastSection = null;
        let sectionBucket = [];
        let sectionWrap = null;
        // Wrapped per-section so the lab filter chips can hide/show a whole
        // section's trend table the same way they hide/show its lab cards.
        const flushSection = () => {
            if (!sectionBucket.length) return;
            sectionWrap.appendChild(buildTrendsTable(sectionBucket));
            sectionBucket = [];
        };
        for (const a of analytes) {
            if (a.section !== lastSection) {
                flushSection();
                sectionWrap = document.createElement('div');
                sectionWrap.dataset.trendSection = a.section || '';
                const heading = document.createElement('h4');
                heading.className = 'lab-section-heading';
                heading.textContent = a.section || 'Other';
                sectionWrap.appendChild(heading);
                elements.trendsContainer.appendChild(sectionWrap);
                lastSection = a.section;
            }
            sectionBucket.push(a);
        }
        flushSection();

        if (elements.trendsSubtitle) {
            elements.trendsSubtitle.textContent = `${analytes.length} analytes · ${colDates.length} most recent dates`;
        }
        elements.trendsSection.hidden = false;

        // Serialize the trend table for the AI lab-analysis button — but only
        // the analytes that carry at least one pathological value (flagged
        // H/L, or numerically outside the reference interval). A normal panel
        // is not worth a model call: labHasAbnormal drives a direct "all
        // normal" card instead (see runLabSummary).
        const isAbnormal = (m, a) => {
            if (m.flag === 'H' || m.flag === 'L') return true;
            if (m.v == null) return false;
            return (a.low != null && m.v < a.low) || (a.high != null && m.v > a.high);
        };
        const header = ['Analyte', 'Interval', ...colDates].join(' | ');
        // Only flag an analyte abnormal if it is out of range within the same
        // 5-most-recent-dates window that is actually sent (colDates), not
        // anywhere in its full history.
        const colSet = new Set(colDates);
        const abnormalAnalytes = analytes.filter(a => a.measurements.some(
            m => colSet.has(m.date?.slice(0, 10)) && isAbnormal(m, a)));
        // Shared by labAiText (abnormal-only) and renalLabAiText (renal
        // analytes, any value) below — same row shape, different filter.
        const serializeAnalyteRows = (list) => list.map(a => {
            const byDate = {};
            for (const m of a.measurements) byDate[m.date?.slice(0, 10) || ''] = m;
            const interval = a.ref
                || (a.low != null && a.high != null ? `${a.low}-${a.high}` : (a.low != null ? `>${a.low}` : (a.high != null ? `<${a.high}` : '')));
            const cells = colDates.map(d => {
                const m = byDate[d];
                if (!m) return '';
                const val = m.v !== null ? (Number.isInteger(m.v) ? m.v : parseFloat(m.v.toPrecision(4))) : (m.text || '');
                return `${val}${m.flag ? ' (' + m.flag + ')' : ''}`;
            });
            const name = `${a.section ? a.section + ' — ' : ''}${a.name}${a.unit ? ' [' + a.unit + ']' : ''}`;
            return [name, interval, ...cells].join(' | ');
        });
        const rows = serializeAnalyteRows(abnormalAnalytes);
        labHasAbnormal = abnormalAnalytes.length > 0;
        // Short context header — same reasoning as buildImagingCardHeader:
        // grounds lab.md's interpretation with who the analytes belong to.
        const patientData = pendingAnalysesData?.patientData;
        const labHeader = patientContextHeader(patientData);
        labAiText = labHasAbnormal ? labHeader + [header, ...rows].join('\n') : '';

        const renalAnalytes = analytes.filter(a => RENAL_ANALYTE_RE.test(a.name));
        const renalRows = serializeAnalyteRows(renalAnalytes);
        renalLabAiText = renalRows.length ? [header, ...renalRows].join('\n') : '';
        if (elements.copyLabBtn) {
            elements.copyLabBtn.hidden = !labHasAbnormal;
            elements.trendsContainer.dataset.markdown = labHasAbnormal
                ? labHeader + `# Lab Trends — Abnormal Analytes\n\n| ${header} |\n| ${header.split(' | ').map(() => '---').join(' | ')} |\n${rows.map(r => `| ${r} |`).join('\n')}`
                : '';
        }
        if (elements.aiLabBtn) {
            elements.aiLabBtn.hidden = false;
            elements.aiLabBtn._aiCard = null;
            if (labHasAbnormal) {
                // Silently redisplay a previously generated summary for this lab-trend text, if any.
                runAiSummary(elements.aiLabBtn, 'lab',
                    () => elements.trendsContainer?.firstChild || null, () => labAiText,
                    { intoAnchorParent: () => elements.trendsContainer, inline: true, auto: true });
            }
        }
        if (elements.contrastSafetyBtn) {
            elements.contrastSafetyBtn.hidden = false;
            elements.contrastSafetyBtn._aiCard = null;
            // Auto-probe only — never triggers loadReportLazily on its own
            // (unlike a real click via runContrastSafetyCheck): if the
            // clinical record hasn't loaded yet, buildContrastSafetyText()
            // still returns a valid (renal-only) text, just one that's very
            // unlikely to already be cached, so this is a harmless no-op.
            runAiSummary(elements.contrastSafetyBtn, 'contrast_safety',
                () => elements.trendsContainer?.firstChild || null, buildContrastSafetyText,
                { intoAnchorParent: () => elements.trendsContainer, inline: true, auto: true });
        }
    }

    async function loadTrends(patientId) {
        if (!patientId || !elements.trendsSection) return;
        const sd = new Date();
        sd.setDate(sd.getDate() - 90);
        const startDate = localDateStr(sd);
        try {
            const resp = await apiFetch(`/api/observation?patient=${encodeURIComponent(patientId)}&start_date=${startDate}`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data.observations?.length) return;
            renderTrends(data.observations);
        } catch (e) {
            console.warn('Trends load failed:', e);
            showToast('Failed to load trends', 'warning');
        }
    }

    const MODALITY_INFO = {
        radio:  { icon: 'mod-radio',  label: 'X-Ray' },
        ct:     { icon: 'mod-ct',     label: 'CT' },
        irm:    { icon: 'mod-irm',    label: 'MRI' },
        eco:    { icon: 'mod-eco',    label: 'Ultrasound' },
        rads:   { icon: 'mod-fluoro', label: 'Fluoroscopy' },
        fluoro: { icon: 'mod-fluoro', label: 'Fluoroscopy' },
        lab:    { icon: 'mod-lab',    label: 'Laboratory' },
    };

    const MODALITY_AVATAR = {
        radio:  { icon: 'mod-radio',  cls: 'mod-xr' },
        ct:     { icon: 'mod-ct',     cls: 'mod-ct' },
        irm:    { icon: 'mod-irm',    cls: 'mod-mr' },
        eco:    { icon: 'mod-eco',    cls: 'mod-us' },
        fluoro: { icon: 'mod-fluoro', cls: 'mod-fl' },
        rads:   { icon: 'mod-fluoro', cls: 'mod-fl' },
        lab:    { icon: 'mod-lab',    cls: 'mod-lab' },
    };
    function modAvatarHTML(slug) {
        const id = MODALITY_AVATAR[slug]?.icon || 'mod-lab';
        return `<svg aria-hidden="true" focusable="false"><use href="#${id}"></use></svg>`;
    }

    // Helper function to create analysis card
    function createAnalysisCard(serviceRequest, analysisType, analysisText) {
        const cardTemplate = document.getElementById('analysis-card-template');
        if (!cardTemplate) { console.error('Analysis card template not found'); return document.createElement('div'); }
        const frag = cardTemplate.content.cloneNode(true);
        const article = frag.querySelector('article');
        if (!article) { console.error('Failed to clone analysis card template'); return document.createElement('div'); }

        article.className = `analysis-card tab-card ${analysisType}`;
        article.dataset.type = analysisType;
        article.dataset.serviceRequestId = serviceRequest.id;
        article.dataset.analysisType = analysisType;

        const modality = MODALITY_INFO[analysisType] || { icon: 'fa-file-medical', label: analysisText };
        // Modality circle avatar
        const circleEl = article.querySelector('.mod-circle');
        if (circleEl) {
            const circleAvatar = MODALITY_AVATAR[analysisType] || { icon: 'fa-question', cls: '' };
            // Preserve the PACS-confirmed badge (in the template markup)
            // across this innerHTML overwrite — see buildTimelineRow's
            // identical pacsBadge handling for the schedule row avatar.
            const pacsBadge = circleEl.querySelector('.pacs-confirmed-badge');
            circleEl.innerHTML = modAvatarHTML(analysisType);
            if (pacsBadge) {
                circleEl.appendChild(pacsBadge);
                pacsBadge.dataset.requestId = serviceRequest.id;
                pacsStatusObserver.observe(circleEl);
            }
            if (circleAvatar.cls) circleEl.classList.add(circleAvatar.cls);
        }

        const typeText = article.querySelector('.type-text');
        if (typeText) {
            typeText.textContent = analysisText || modality.label;
            typeText.style.cursor = 'pointer';
            typeText.title = 'Click to copy DokuLLM ID';
            typeText.addEventListener('click', (e) => {
                e.stopPropagation();
                copyTextToClipboard(buildExamIdStub(pendingAnalysesData?.patientData, serviceRequest.date_time));
            });
        }

        const reportId = article.querySelector('.report-id');
        if (reportId) {
            if (hipocrateUrl) {
                const a = document.createElement('a');
                a.href = `${hipocrateUrl}/PARA/NOM/Listare/cerere.asp?id=${serviceRequest.id}`;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.textContent = `#${serviceRequest.id}`;
                reportId.appendChild(a);
            } else {
                reportId.textContent = `#${serviceRequest.id}`;
            }
        }

        const examDateEl = article.querySelector('.exam-date');
        if (examDateEl && serviceRequest.date_time) {
            examDateEl.textContent = formatExamDate(serviceRequest.date_time);
            examDateEl.dateTime = serviceRequest.date_time;
        }

        // Body regions → part of the card title
        const regions = (serviceRequest.regions || []).filter(Boolean);
        const regionsEl = article.querySelector('.card-regions');
        if (regionsEl && regions.length > 0) {
            regionsEl.textContent = ` · ${regions.join(', ')}`;
        }
        // Patient/exam stub click target: bound to the whole title line, not
        // just .card-regions — that span is empty (zero-width, unclickable)
        // whenever the regions list couldn't be resolved, which silently killed this
        // for any exam without a mapped region. typeText's own listener
        // (above) stops propagation, so clicking the modality name still
        // copies the DokuLLM ID; clicking anywhere else in the title —
        // region or indication text — copies the patient stub.
        const titleEl = article.querySelector('.card-title');
        if (titleEl) {
            titleEl.style.cursor = 'pointer';
            titleEl.title = 'Click to copy patient/exam stub';
            titleEl.addEventListener('click', (e) => {
                e.stopPropagation();
                copyTextToClipboard(buildExamStub(article));
            });
        }

        // Urgent: red border only
        if (serviceRequest.is_urgent) {
            article.classList.add('urgent-card');
        }

        // Ordering physician (from ServiceRequest.requester)
        const referrer = serviceRequest.medic;
        const referrerEl = article.querySelector('.card-referrer');
        if (referrerEl && referrer) {
            referrerEl.textContent = referrer;
            const line = article.querySelector('.card-referrer-line');
            if (line) line.hidden = false;
        }

        // Clinical indication — show inline next to physician
        // Remove write/perform/validate controls from non-imaging cards immediately
        // (type is known now) — a radiologist has no access to write lab reports.
        if (!IMAGING_TYPES.includes(analysisType)) {
            article.querySelector('.btn-write-report')?.remove();
            article.querySelector('.btn-perform-exam')?.remove();
            article.querySelector('.validate-toggles')?.remove();
            article.querySelector('.report-actions')?.remove();
        }

        return article;
    }

    // Short context header prepended to an imaging card's copied/AI-analysed
    // markdown: patient demographics, indication, exam date/time, and
    // modality — grounds imaging.md's dominant-finding call the same way the
    // visible card already grounds a human reader.
    function buildImagingCardHeader(article, data, type) {
        const parts = [];
        const patientData = pendingAnalysesData?.patientData;
        if (patientData) {
            const age = calculateAge(patientData.birth_date);
            const gender = formatGender(patientData.sex);
            const demo = [gender, age].filter(v => v && v !== 'N/A').join(', ');
            if (demo) parts.push(`**Patient:** ${demo}`);
        }
        const indication = article.querySelector('.card-indication-text')?.textContent
            ?.replace(/^\s*·\s*/, '').trim();
        if (indication) parts.push(`**Indication:** ${indication}`);
        const when = data.date ? formatDateWithTime(data.date) : '';
        if (when && when !== 'Unknown') parts.push(`**Date/time:** ${when}`);
        // The card's own known type/region — set from the request row and
        // reliably correct.
        const examType = article.querySelector('.type-text')?.textContent
            || MODALITY_INFO[type]?.label;
        const region = article.querySelector('.card-regions')?.textContent
            ?.replace(/^\s*·\s*/, '').trim();
        const exam = [examType, region].filter(Boolean).join(' · ');
        if (exam) parts.push(`**Examination:** ${exam}`);
        if (!parts.length) return '';
        return parts.join('  \n') + '\n\n---\n\n';
    }

    // Bounds the imaging_trend AI synopsis's prompt size — same tunable-
    // constant pattern as EPISODE_GAP_DAYS/SPARSE_THRESHOLD.
    const IMAGING_EPISODE_STUDY_CAP = 8;

    // Dated, chronological (oldest→newest) markdown fed to the imaging_trend
    // AI synopsis — same "grounding header + per-item blocks" shape as
    // labAiText, and the same "fetch more candidates than the cap, keep the
    // first N with usable content" skimming the Report tab's §3 uses.
    // `list` arrives most-recent-first (populateStudyGrid's current-episode
    // partition); returns '' if nothing has a usable report body.
    async function buildImagingEpisodeText(list, patientData) {
        const candidates = list.slice(0, IMAGING_EPISODE_STUDY_CAP * 2);
        const parts = await limitedMap(candidates, MAX_CONCURRENT_REQUESTS,
            e => getImagingReportParts(e.id));

        const kept = [];
        for (let i = 0; i < candidates.length && kept.length < IMAGING_EPISODE_STUDY_CAP; i++) {
            // _isMeaningfulText, not plain truthiness: a report body can be
            // non-empty but placeholder junk (e.g. "-", ". .." — doctors
            // sometimes type that just to pass form validation), which
            // would otherwise feed the model a fake "study" with no real
            // content.
            if (_isMeaningfulText(parts[i]?.body)) kept.push({ sr: candidates[i], parts: parts[i] });
        }
        if (!kept.length) return '';
        kept.reverse(); // oldest → newest, as the prompt expects

        const header = patientContextHeader(patientData);

        const blocks = kept.map(({ sr, parts: p }) => {
            const mod = sr.type || '';
            const modLabel = MODALITY_INFO[mod]?.label || mod;
            const region = (sr.regions || []).filter(Boolean).join(', ');
            const date = sr.date_time ? formatDate(sr.date_time) : 'Unknown date';
            // Date, modality (+ region), and the clinical info attached to
            // this exam all live in the heading itself now — previously the
            // indication was a separate line below, easy to lose track of
            // across a long multi-study timeline.
            const title = [modLabel, region].filter(Boolean).join(' · ');
            const clinicalInfo = _isMeaningfulText(p.indication) ? ` — ${p.indication}` : '';
            const block = `### ${date} — ${title}${clinicalInfo}\n\n${p.body}`;
            return block;
        });

        return header + blocks.join('\n\n');
    }

    // Builds the "Current Episode" heading row for the Imaging grid, with an
    // AI | Copy toolbar (mirrors Lab Trends' #aiLabBtn/#copyLabBtn pair) —
    // only used when the episode has more than one study to compare. The
    // episode text is built lazily on first AI/Copy click (not eagerly at
    // grid render), since it requires fetching each study's full report body
    // — work the app otherwise defers until a card scrolls into view.
    function buildImagingEpisodeHeader(list, patientData) {
        let episodeTextPromise = null;
        const getEpisodeText = () => episodeTextPromise ||= buildImagingEpisodeText(list, patientData);

        const headerRow = document.createElement('div');
        headerRow.className = 'episode-header';

        const heading = document.createElement('h3');
        heading.className = 'episode-divider';
        heading.textContent = 'Current Episode';

        const toolbar = document.createElement('div');
        toolbar.className = 'card-toolbar';

        const aiBtn = document.createElement('button');
        aiBtn.type = 'button';
        aiBtn.className = 'btn-ai';
        aiBtn.setAttribute('aria-label', 'AI imaging episode synopsis');
        aiBtn.title = 'AI imaging episode synopsis';
        aiBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i><span>AI</span>';
        aiBtn.addEventListener('click', async () => {
            aiBtn.disabled = true;
            let text;
            try {
                text = await getEpisodeText();
            } catch (err) {
                aiBtn.disabled = false;
                showToast('Failed to load imaging data for AI summary', 'error');
                return;
            }
            // headerRow's next sibling is this section's first card — the AI
            // card is inserted right above it, once headerRow is in the DOM.
            runAiSummary(aiBtn, 'imaging_trend',
                () => headerRow.nextElementSibling, () => text,
                { inline: true, intoAnchorParent: () => headerRow.parentElement });
        });

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn-copy';
        copyBtn.setAttribute('aria-label', 'Copy current episode imaging as Markdown');
        copyBtn.title = 'Copy current episode imaging as Markdown';
        copyBtn.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i>';
        copyBtn.addEventListener('click', async () => {
            copyBtn.disabled = true;
            try {
                headerRow.dataset.markdown = await getEpisodeText();
            } catch (err) {
                headerRow.dataset.markdown = '';
            }
            copyBtn.disabled = false;
            // copyMarkdown itself no-ops with a toast if dataset.markdown is empty.
            copyMarkdown(headerRow, copyBtn, () => flashIcon(copyBtn));
        });

        toolbar.append(aiBtn, copyBtn);
        headerRow.append(heading, toolbar);

        // Silently redisplay a previously generated synopsis (mirrors
        // report/epicrisis/pre_exam_brief/lab/per-study-imaging's opts.auto probe)
        // — unlike those, deferred to this header scrolling into view rather
        // than run at render time, since building the episode text requires
        // fetching every study's report body (the same fetch getEpisodeText
        // already defers to first click). Without this, a cached synopsis
        // for the current episode never surfaces until the user clicks AI,
        // which always regenerates (force:true) — see aiSummarizeStream.
        const autoObserver = new IntersectionObserver(async (observed, obs) => {
            if (!observed.some(e => e.isIntersecting)) return;
            obs.disconnect();
            let text;
            try {
                text = await getEpisodeText();
            } catch (_) {
                return; // silent — mirrors opts.auto's own failure handling
            }
            if (!text) return;
            runAiSummary(aiBtn, 'imaging_trend',
                () => headerRow.nextElementSibling, () => text,
                { inline: true, intoAnchorParent: () => headerRow.parentElement, auto: true });
        });
        autoObserver.observe(headerRow);

        return headerRow;
    }

    function setCardIndication(article, text) {
        if (!text) return;
        const indText = article.querySelector('.card-indication-text');
        if (indText) indText.textContent = ' · ' + text;
    }

    async function fetchAndFillReport(article) {
        const id = article.dataset.serviceRequestId;
        const type = article.dataset.analysisType;
        const imagingTypes = ['radio', 'ct', 'irm', 'eco', 'rads'];
        const endpoint = imagingTypes.includes(type)
            ? `/api/study/${id}`
            : `/api/report/${id}`;

        // Resolve whoami up front — this function can fire from the
        // IntersectionObserver right after page load, racing the in-flight
        // fetchWhoami() call. Reading canWriteReports before it settles (it's
        // used below, well before the old await point) would silently treat
        // an allowed radiologist as read-only on the first render pass after
        // a reload.
        await whoamiReady;
        // The automatic whoami fired by initApp() is fire-and-forget with a
        // silent catch — if that one attempt failed (e.g. a cold Hipocrate
        // session right after reload), nothing retries it and the user is
        // stuck read-only for the rest of the session (previously only
        // fixed by opening the account modal, which happens to retry).
        // Self-heal here instead: retry once if it never got whoamiData.
        if (!whoamiData) {
            whoamiReady = fetchWhoami().catch(() => {});
            await whoamiReady;
        }

        const loadingEl = article.querySelector('.report-loading');
        const bodyEl    = article.querySelector('.report-body');

        // Reset report content before re-fetching so stale injected text doesn't duplicate
        article.querySelector('.report-preview')?.replaceChildren();
        article.classList.remove('no-report');
        // Reset the copy button; re-revealed below only when a report exists
        const cardCopyBtn = article.querySelector('.btn-card-copy');
        if (cardCopyBtn) { cardCopyBtn.hidden = true; cardCopyBtn.onclick = null; }
        // Reset the AI triage button; re-revealed only for imaging reports.
        // Also drop any card left over from a prior render of this article
        // (fetchAndFillReport can re-run via the perform/write refresh path).
        const cardAiBtn = article.querySelector('.btn-card-ai');
        if (cardAiBtn) { cardAiBtn.hidden = true; cardAiBtn._aiCard = null; }
        article.querySelector('.card-report-section .ai-summary-card')?.remove();

        let hasReportFromStudy = false;
        try {
            const resp = await apiFetch(endpoint);
            if (!resp.ok) throw new Error(resp.status);
            const data = reportFromApi(await resp.json(), imagingTypes.includes(type));

            // Ordering physician from referrer (if not already set from ServiceRequest)
            const referrerEl = article.querySelector('.card-referrer');
            if (referrerEl && !referrerEl.textContent && data.requester) {
                referrerEl.textContent = data.requester;
                const line = article.querySelector('.card-referrer-line');
                if (line) line.hidden = false;
            }

            // Clinical indication → show inline next to physician
            const resultNotes = data.results;
            if (data.indication) {
                const existing = article.querySelector('.card-indication-text');
                if (!existing?.textContent) setCardIndication(article, data.indication);
            }

            // ImagingStudy's own note (BuletinAnalize.asp's INFO SUPLIMENTAR) is
            // often empty even when a clinical indication was recorded on the
            // request itself (Justificare / Situatie clinica on
            // BuletinSolicitare.asp). Fall back to the same per-request fetch
            // the Schedule tab already uses for this (scheduleExamObserver).
            // Also the only source for the TRUE ordering physician ("Medic
            // solicitant") — the referrer set above at populate-time comes
            // from the listing's "medic" column, which is "Medic curant" (the
            // attending physician), a different person whenever the patient's
            // regular doctor isn't the one who placed this specific order.
            if (imagingTypes.includes(type)) {
                try {
                    const srResp = await apiFetch(`/api/request/${id}`);
                    if (srResp.ok) {
                        const srData = (await srResp.json()).request || {};
                        if (!article.querySelector('.card-indication-text')?.textContent) {
                            const srIndication = srData.indication || '';
                            if (_isMeaningfulText(srIndication)) setCardIndication(article, srIndication);
                        }
                        const srReferrer = srData.requester;
                        if (referrerEl && _isMeaningfulText(srReferrer)) {
                            referrerEl.textContent = srReferrer;
                            const line = article.querySelector('.card-referrer-line');
                            if (line) line.hidden = false;
                        }
                    }
                } catch (_) { /* best-effort */ }
            }

            // Report text
            const forms = data.forms;
            const hasReport = forms.length > 0
                || resultNotes.some(n => n.text);
            hasReportFromStudy = hasReport;

            // Store raw text so the editor modal can pre-populate
            if (canWriteReports) {
                const rawParts = forms.length > 0
                    ? forms.filter(f => f.data && !f.reference).map(f => f.data)
                    : resultNotes.filter(n => n.text).map(n => n.text);
                article.dataset.reportText = rawParts.join('\n\n');
            }

            // Signature footer only when a report actually exists — without one,
            // performer falls back to the requesting physician server-side and
            // showing it here would misattribute the (nonexistent) report
            if (hasReport) {
                const physician = data.examiner;
                const medicEl = article.querySelector('.card-medic');
                if (medicEl && physician) medicEl.textContent = physician;
                // Only show signature footer when a physician is present
                const signedEl = article.querySelector('.report-signed');
                if (signedEl) signedEl.hidden = !physician;
            }

            // Markdown for the header copy button, accumulated per branch below.
            // Lab cards copy a concise value table; imaging/other cards copy the
            // report text. Empty → button stays hidden.
            let copyMd = '', copyIsLab = false;

            const reportPreview = article.querySelector('.report-preview');
            if (reportPreview) {
                const notes = resultNotes;
                if (forms.length > 0) {
                    const allLab = forms.every(f => f.type === 'lab' || f.reference !== undefined);
                    if (allLab) {
                        reportPreview.appendChild(buildLabTable(forms));
                        copyMd = buildLabMarkdown(forms);
                        copyIsLab = true;
                        // Tag card with lab sections for dynamic chip filtering
                        const sections = [...new Set(forms.map(f => f.section).filter(Boolean))];
                        if (sections.length) {
                            article.dataset.labSection = sections.join('\t');
                            if (article.closest('#labGrid')) addLabChips(sections);
                        }
                    } else {
                        for (const form of forms) {
                            if (forms.length > 1 && form.title) {
                                const h3 = document.createElement('h3');
                                h3.className = 'study-title';
                                h3.textContent = form.title;
                                reportPreview.appendChild(h3);
                            }
                            if (form.contentType === 'text/markdown' && form.data) {
                                const div = document.createElement('div');
                                div.innerHTML = marked.parse(form.data);
                                reportPreview.appendChild(div);
                            } else if (form.contentType === 'text/html' && form.data) {
                                const div = document.createElement('div');
                                div.innerHTML = form.data;
                                reportPreview.appendChild(div);
                            } else if (form.contentType === 'text/plain' && form.data) {
                                const pre = document.createElement('pre');
                                pre.textContent = form.data;
                                reportPreview.appendChild(pre);
                            }
                        }
                        copyMd = forms
                            .map(f => (forms.length > 1 && f.title) ? `##### ${f.title}\n\n${f.data || ''}` : (f.data || ''))
                            .filter(s => s.trim())
                            .join('\n\n---\n\n')
                            .trim();
                    }
                } else if (notes.length > 0) {
                    notes.forEach(note => {
                        if (!note.text) return;
                        if (note.title) {
                            const titleEl = document.createElement('p');
                            titleEl.className = 'series-result-title';
                            titleEl.textContent = note.title;
                            reportPreview.appendChild(titleEl);
                        }
                        const div = document.createElement('div');
                        div.className = 'report-note';
                        // Collapse \n\n paragraph breaks to \n so marked
                        // renders lines as <br> (tight list) not spaced <p> blocks
                        const normalised = note.text.replace(/\n{2,}/g, '\n');
                        div.innerHTML = marked.parse(normalised).trim();
                        reportPreview.appendChild(div);
                    });
                    copyMd = notes
                        .map(note => {
                            if (!note.text) return '';
                            const t = note.title ? `##### ${note.title}\n\n` : '';
                            return t + note.text.trim();
                        })
                        .filter(Boolean)
                        .join('\n\n');
                } else {
                    article.classList.add('no-report');
                }
            }

            // Prepend a short context header (demographics, indication, date/time,
            // exam type) — same markdown feeds both the copy button and imaging.md.
            if (copyMd && !copyIsLab && imagingTypes.includes(type)) {
                const header = buildImagingCardHeader(article, data, type);
                if (header) copyMd = header + copyMd;
            }

            // Reveal the header copy button once report content is known.
            // Same icon-only control for lab and imaging; only the label differs.
            // onclick (not addEventListener) stays idempotent across re-renders.
            if (cardCopyBtn && copyMd) {
                const label = copyIsLab ? 'Copy lab values as Markdown' : 'Copy report as Markdown';
                cardCopyBtn.dataset.markdown = copyMd;
                cardCopyBtn.title = label;
                cardCopyBtn.setAttribute('aria-label', label);
                cardCopyBtn.hidden = false;
                cardCopyBtn.onclick = () => copyMarkdown(cardCopyBtn, cardCopyBtn, () => flashIcon(cardCopyBtn));
            }

                // AI triage summary — imaging reports only (not lab value tables).
                // Uses the report markdown; card renders above the report body.
                if (cardAiBtn && copyMd && !copyIsLab) {
                    cardAiBtn.dataset.aiText = copyMd;
                    cardAiBtn.hidden = false;
                    cardAiBtn.onclick = () => runAiSummary(
                        cardAiBtn, 'imaging',
                        () => article.querySelector('.report-body'),
                        () => cardAiBtn.dataset.aiText || '',
                        { inline: true });
                // Silently redisplay a previously generated summary for this
                // report, if any (mirrors lab/epicrisis/report/pre_exam_brief).
                runAiSummary(
                    cardAiBtn, 'imaging',
                    () => article.querySelector('.report-body'),
                    () => cardAiBtn.dataset.aiText || '',
                    { inline: true, auto: true });
                //enqueueAiWarm('imaging', copyMd, dataGeneration);
                }
        } catch (_) {
            article.classList.add('no-report');
        } finally {
            if (loadingEl) loadingEl.hidden = true;
            if (bodyEl) bodyEl.hidden = false;

            // Lab requests with no report data yet (not performed / no results)
            // clutter the grid with empty cards a radiologist can't act on
            // (no write access — see createAnalysisCard). Drop them instead.
            if (!IMAGING_TYPES.includes(type) && article.classList.contains('no-report')) {
                article.remove();
                if (elements.labCount) {
                    const n = parseInt(elements.labCount.textContent, 10);
                    if (!Number.isNaN(n)) elements.labCount.textContent = Math.max(0, n - 1);
                }
                if (elements.labGrid && elements.labNoData && !elements.labGrid.querySelector('.analysis-card')) {
                    elements.labNoData.style.display = 'block';
                }
                return;
            }

            // Fetch cerere.asp state (investigation names/text + per-analysis validate
            // info) for every imaging card, regardless of write access — a read-only
            // viewer should still see each investigation's name and pending status,
            // just without the Perform/Edit/validate controls (canWriteReports-gated
            // below). /api/request/{id}/patient only requires auth, not radiologist
            // write access, so this call is safe for any logged-in user.
            // (whoamiReady already awaited at the top of this function.)
            if (IMAGING_TYPES.includes(type)) {
                const writeBtn = article.querySelector('.btn-write-report');
                const actionGroup = article.querySelector('.action-group');
                if (canWriteReports) {
                    // Perform/Cancel/Edit stay visible throughout — only their
                    // enabled/disabled state changes below, so the toolbar
                    // doesn't shift around as the request moves through states.
                    // Disabled by default until the fetch below confirms the real
                    // state, so nothing is clickable during the loading window.
                    if (writeBtn) { writeBtn.hidden = false; writeBtn.disabled = true; }
                    if (actionGroup) {
                        actionGroup.hidden = false;
                        actionGroup.querySelectorAll('button').forEach(b => { b.disabled = true; });
                    }
                    const togglesElReset = article.querySelector('.validate-toggles');
                    if (togglesElReset) { togglesElReset.hidden = true; togglesElReset.replaceChildren(); }
                }
                // write button is shown after cerere fetch confirms editable analyses exist
                const cerereId = article.dataset.serviceRequestId;
                try {
                    const r = await fetch(`/api/request/${cerereId}/patient`, { headers: authHeader() });
                    const d = await r.json();
                    const analyses = Array.isArray(d.report) ? d.report
                        : (d.report && typeof d.report === 'object' ? [d.report] : []);
                    // Store for editor
                    article.dataset.reportAnalyses = JSON.stringify(analyses);

                    // Ensure every requested investigation is represented in the preview,
                    // not just the ones already reported/validated (BuletinAnalize only
                    // renders series that have real content). A multi-step request (e.g.
                    // anesthesia + the scan itself) previously lost any step without text
                    // — invisible if none had text yet, or silently dropped if some did.
                    // Match by label against titles already rendered from real content;
                    // anything left over gets its own title + "Not yet reported." note,
                    // formatted identically, so every step reads the same way.
                    const previewEl = article.querySelector('.report-preview');
                    if (previewEl && analyses.length) {
                        const existingTitles = new Set(
                            [...previewEl.querySelectorAll('.series-result-title')]
                                .map(t => (t.firstChild?.textContent ?? '').trim())
                        );
                        const missing = analyses.filter(a => !a.label || !existingTitles.has(a.label.trim()));
                        const showTitles = analyses.length > 1 || analyses[0]?.label;
                        for (const a of missing) {
                            if (showTitles && a.label) {
                                const titleEl = document.createElement('p');
                                titleEl.className = 'series-result-title';
                                titleEl.textContent = a.label;
                                previewEl.appendChild(titleEl);
                            }
                            const div = document.createElement('div');
                            if (a.text) {
                                div.className = 'report-note';
                                div.innerHTML = marked.parse(a.text).trim();
                            } else {
                                div.className = 'report-note report-note-pending';
                                div.textContent = 'Not yet reported.';
                            }
                            previewEl.appendChild(div);
                        }
                        if (missing.length) article.classList.remove('no-report');
                    }

                    const hasReport    = analyses.some(a => a.text);
                    const isEditable   = analyses.some(a => a.editable);
                    const allValidated = analyses.length > 0 && analyses.every(a => a.validated);
                    // Treat as performed if: DataEfectuarii set, all cerere analyses validated,
                    // or BuletinAnalize already has a published report (cerere.asp may not render
                    // fn_validate_cerere calls once the exam is fully finalised in Hipocrate)
                    const performed    = Boolean(d.performed_at) || allValidated || hasReportFromStudy;
                    // cerere.asp itself confirms cancellation (its header div's "Status :"
                    // field reads "Cerere anulata", plus a "CEREREA ESTE ANULATA" banner —
                    // see HippoClientCerere.parse_data) — d.cancelled is that server-
                    // confirmed truth, so it survives reload/other sessions unlike a
                    // purely local flag. The local flag (set by cancelRequest() right
                    // after a successful /cancel call) is kept as an optimistic fallback
                    // in case this fetch races ahead of Hipocrate's own state update.
                    const cancelled = Boolean(d.cancelled) || article.dataset.cancelled === '1';

                    if (performed) article.classList.remove('no-report');

                    if (canWriteReports) {
                    // Perform + Cancel: active until performed or cancelled, then
                    // locked (disabled, muted) instead of disappearing.
                    if (actionGroup) {
                        const locked = performed || cancelled;
                        let performBtn = actionGroup.querySelector('.btn-perform-exam');
                        if (performBtn) {
                            performBtn.replaceWith(performBtn.cloneNode(true));
                            performBtn = actionGroup.querySelector('.btn-perform-exam');
                            performBtn.disabled = locked;
                            if (!locked) {
                                performBtn.addEventListener('click', () => markExamPerformed(article, cerereId));
                            }
                        }
                        let cancelBtn = actionGroup.querySelector('.btn-cancel-request');
                        if (cancelBtn) {
                            cancelBtn.replaceWith(cancelBtn.cloneNode(true));
                            cancelBtn = actionGroup.querySelector('.btn-cancel-request');
                            cancelBtn.disabled = locked;
                            if (!locked) {
                                cancelBtn.addEventListener('click', () => cancelRequest(article, cerereId));
                            }
                        }
                    }

                    // Edit: disabled until performed; once performed, enabled only
                    // while there's still an editable, not-fully-validated analysis.
                    if (writeBtn) {
                        const editable = performed && isEditable && !allValidated;
                        writeBtn.replaceWith(writeBtn.cloneNode(true));
                        const wb = article.querySelector('.btn-write-report');
                        wb.disabled = !editable;
                        if (editable) {
                            wb.addEventListener('click', () => openReportEditor(article));
                        }
                    }

                    // States 3 & 4: performed + report exists → validate toggles
                    const togglesEl = article.querySelector('.validate-toggles');
                    if (togglesEl && performed && hasReport && analyses.length) {
                        const previewTitles = [...(previewEl?.querySelectorAll('.series-result-title') || [])];
                        const allCbs = () => [...article.querySelectorAll('input[type="checkbox"][aria-label^="Validated"]')];

                        for (let i = 0; i < analyses.length; i++) {
                            const analysis = analyses[i];

                            const inp = document.createElement('input');
                            inp.type = 'checkbox';
                            inp.checked = analysis.validated;
                            inp.setAttribute('aria-label', `Validated: ${analysis.label}`);
                            const slider = document.createElement('span');
                            slider.className = 'switch-slider';
                            const lbl = document.createElement('label');
                            lbl.className = 'switch';
                            lbl.append(inp, slider);

                            inp.addEventListener('change', () => {
                                const allChecked = allCbs().every(cb => cb.checked);
                                const wb = article.querySelector('.btn-write-report');
                                if (wb) wb.hidden = allChecked;
                                setValidated(article, cerereId, analysis.anl_id, analysis.id_grup, inp.checked);
                            });

                            // Inject into the matching series-result-title (by exact label —
                            // never by array position: a positional fallback here used to
                            // attach one analysis's checkbox into a completely unrelated
                            // title's row whenever label text didn't match exactly). The
                            // preview-completion pass above gives every analysis a title,
                            // so this should always match; the standalone row below is a
                            // safety net for any label mismatch.
                            const titleEl = previewTitles.find(t => t.firstChild?.textContent?.trim() === analysis.label?.trim());
                            if (titleEl) {
                                titleEl.appendChild(lbl);
                            } else {
                                const fmtLabel = (checked) => {
                                    const status = checked ? 'Valid' : 'Invalid';
                                    return analyses.length > 1 ? `${analysis.label}: ${status}` : status;
                                };
                                const labelText = document.createElement('span');
                                labelText.className = 'switch-label';
                                labelText.textContent = fmtLabel(analysis.validated);
                                inp.addEventListener('change', () => { labelText.textContent = fmtLabel(inp.checked); });
                                const row = document.createElement('div');
                                row.className = 'validate-row';
                                row.append(lbl, labelText);
                                togglesEl.appendChild(row);
                                togglesEl.hidden = false;
                            }
                        }
                    }
                    }
                } catch (_) {}
            }
        }
    }

    async function setValidatedCore(cerereId, anlId, idGrup, validated, { onDone }) {
        const resp = await fetch(`/api/request/${cerereId}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeader() },
            body: JSON.stringify({ anl_id: anlId, id_grup: idGrup, validated })
        });
        if (!resp.ok) {
            showToast(await resp.text(), 'error');
            return;
        }
        onDone();
    }

    async function setValidated(article, cerereId, anlId, idGrup, validated) {
        await setValidatedCore(cerereId, anlId, idGrup, validated, {
            onDone: () => fetchAndFillReport(article)
        });
    }

    async function markExamPerformedCore(cerereId, { setDisabled, onDone }) {
        setDisabled(true);
        const resp = await fetch(`/api/request/${cerereId}/perform`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeader() },
            body: JSON.stringify({}), // no performed_at — server defaults to now()
        });
        if (!resp.ok) {
            setDisabled(false);
            showToast(await resp.text().catch(() => `HTTP ${resp.status}`), 'error');
            return;
        }
        showToast('Exam marked as performed', 'success');
        onDone();
    }

    async function markExamPerformed(article, cerereId) {
        const btn = article.querySelector('.btn-perform-exam');
        const sibling = article.querySelector('.btn-cancel-request');
        await markExamPerformedCore(cerereId, {
            // Lock both buttons while in flight — Perform and Cancel act on
            // the same request, so nothing should fire a concurrent racing
            // call against it while the other is still in progress.
            setDisabled: (v) => { if (btn) btn.disabled = v; if (sibling) sibling.disabled = v; },
            onDone: () => fetchAndFillReport(article),
        });
    }

    async function cancelRequestCore(cerereId, { setDisabled, onDone }) {
        if (!confirm('Cancel this request? This cannot be undone.')) return;
        setDisabled(true);
        const resp = await fetch(`/api/request/${cerereId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeader() },
            body: JSON.stringify({}),
        });
        if (!resp.ok) {
            setDisabled(false);
            showToast(await resp.text().catch(() => `HTTP ${resp.status}`), 'error');
            return;
        }
        showToast('Request cancelled', 'success');
        onDone();
    }

    async function cancelRequest(article, cerereId) {
        const btn = article.querySelector('.btn-cancel-request');
        const sibling = article.querySelector('.btn-perform-exam');
        await cancelRequestCore(cerereId, {
            setDisabled: (v) => { if (btn) btn.disabled = v; if (sibling) sibling.disabled = v; },
            onDone: () => {
                article.dataset.cancelled = '1';
                fetchAndFillReport(article);
            }
        });
    }
    
    // Core textarea-editor + save logic, decoupled from any specific card's
    // DOM. Callers pass in the analyses to edit and an onSaved() callback
    // invoked after a successful save (instead of assuming a fixed refresh
    // path), so this can be reused from both the Imaging tab and the
    // Schedule exam modal.
    function openReportEditorCore(cerereId, analyses, { onSaved }) {
        const tmpl = document.getElementById('report-editor-modal-template');
        if (!tmpl) { showToast('Error: report editor template missing', 'error'); return; }
        const modal = tmpl.content.cloneNode(true).querySelector('dialog');
        if (!modal) { showToast('Error: dialog missing in template', 'error'); return; }

        document.body.appendChild(modal);
        modal.showModal();

        const idEl = modal.querySelector('.editor-report-id');
        if (idEl) idEl.textContent = `#${cerereId}`;

        // Build one textarea per editable analysis
        const editable = analyses.filter(a => a.editable);
        const section = modal.querySelector('.editor-analyses');
        const textareas = [];
        for (const analysis of editable) {
            const wrap = document.createElement('div');
            wrap.className = 'editor-analysis';
            if (editable.length > 1) {
                const lbl = document.createElement('label');
                lbl.className = 'editor-analysis-label';
                lbl.textContent = analysis.label;
                wrap.appendChild(lbl);
            }
            const ta = document.createElement('textarea');
            ta.className = 'editor-textarea';
            ta.rows = editable.length > 1 ? 6 : 14;
            ta.placeholder = 'Description and conclusion...';
            ta.value = analysis.text || '';
            wrap.appendChild(ta);
            section.appendChild(wrap);
            textareas.push({ ta, anl_id: analysis.anl_id });
        }
        if (textareas.length) textareas[0].ta.focus();

        const closeModal = () => { modal.close(); modal.remove(); };
        modal.querySelectorAll('[data-close-modal], .close').forEach(b => b.addEventListener('click', closeModal));
        modal.addEventListener('cancel', () => modal.remove());

        modal.querySelector('.editor-save').addEventListener('click', async () => {
            const saveBtn = modal.querySelector('.editor-save');
            saveBtn.disabled = true;
            let errEl = modal.querySelector('.editor-error');

            try {
                for (const { ta, anl_id } of textareas) {
                    const text = ta.value.trim();
                    if (!text) continue;
                    const resp = await apiFetch(`/api/request/${cerereId}/report`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ anl_id, text }),
                    });
                    if (!resp.ok) {
                        const msg = await resp.text().catch(() => `HTTP ${resp.status}`);
                        throw new Error(msg);
                    }
                }
                closeModal();
                onSaved();
                showToast('Report saved.', 'success');
            } catch (err) {
                if (!errEl) {
                    errEl = document.createElement('p');
                    errEl.className = 'editor-error';
                    section.appendChild(errEl);
                }
                errEl.textContent = err.message || 'Error saving report';
                saveBtn.disabled = false;
                showToast(err.message || 'Error saving report', 'error');
            }
        });
    }

    function openReportEditor(article) {
        const cerereId = article.dataset.serviceRequestId;
        const analyses = JSON.parse(article.dataset.reportAnalyses || '[]');
        openReportEditorCore(cerereId, analyses, {
            onSaved: () => {
                const reportBody = article.querySelector('.report-body');
                const reportPreview = article.querySelector('.report-preview');
                if (reportBody) reportBody.hidden = true;
                if (reportPreview) reportPreview.replaceChildren();
                article.classList.remove('no-report');
                fetchAndFillReport(article);
            }
        });
    }

    // Enhanced date formatting function
    // Parse an ISO-ish date string and return YYYY-MM-DD (or YYYY-MM if no day)
    function formatDate(dateString) {
        if (!dateString) return 'Unknown';
        // If it looks like a bare date (YYYY-MM-DD or YYYY-MM), return as-is
        if (/^\d{4}-\d{2}(-\d{2})?$/.test(dateString)) return dateString;
        try {
            const d = new Date(dateString);
            if (isNaN(d)) return dateString;
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${y}-${m}-${day}`;
        } catch { return dateString; }
    }

    function formatDateWithTime(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const d = new Date(dateString);
            if (isNaN(d)) return dateString;
            const date = formatDate(dateString);
            const hh = String(d.getHours()).padStart(2, '0');
            const mm = String(d.getMinutes()).padStart(2, '0');
            return `${date} ${hh}:${mm}`;
        } catch { return dateString; }
    }

    // Human-friendly date for analysis cards: relative label + time for recent, absolute for older
    function formatExamDate(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const d = new Date(dateString);
            if (isNaN(d)) return dateString;
            const hh = String(d.getHours()).padStart(2, '0');
            const mm = String(d.getMinutes()).padStart(2, '0');
            const time = `${hh}:${mm}`;
            const now = new Date();
            const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
            const diffDays = Math.round((startOfToday - startOfDay) / 86400000);
            if (diffDays === 0) return `Today · ${time}`;
            if (diffDays === 1) return `Yesterday · ${time}`;
            if (diffDays > 1 && diffDays < 7) return `${diffDays} days ago · ${time}`;
            return `${formatDate(dateString)} · ${time}`;
        } catch { return dateString; }
    }

    // ── Current episode boundary ────────────────────────────────────────
    // Centralizes the "active admission" heuristic (previously duplicated
    // between displayPatientReport and loadAndDisplayEpicrisis) and extends
    // it to outpatient-only patients via gap-based date clustering, so
    // imaging/lab history can be split into "current episode" vs.
    // "historical episodes" everywhere it's shown.
    const EPISODE_GAP_DAYS = 60; // gap (days) between orders that starts a new episode
    let episodeBoundaryPromise = null; // memoized per patient; reset alongside dataGeneration in clearResults()

    // Parses only the YYYY-MM-DD prefix (never `new Date(hipocrate_string)`
    // on the raw value) into whole UTC days, for gap-day arithmetic only.
    function isoDateToUTCDays(dateStr) {
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || '');
        if (!m) return null;
        return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86400000;
    }

    // Given a set of order dates, finds the start of the most recent cluster
    // — the date right after the last gap exceeding EPISODE_GAP_DAYS.
    function clusterEpisodeStart(dates) {
        const sorted = [...new Set(dates.filter(Boolean))].sort();
        if (!sorted.length) return null;
        let clusterStart = sorted[0];
        let prevDays = isoDateToUTCDays(sorted[0]);
        for (let i = 1; i < sorted.length; i++) {
            const days = isoDateToUTCDays(sorted[i]);
            if (prevDays != null && days != null && (days - prevDays) > EPISODE_GAP_DAYS) {
                clusterStart = sorted[i];
            }
            prevDays = days;
        }
        return clusterStart;
    }

    // dates: flat array of ISO date strings (imaging + lab order dates) used
    // only for the outpatient gap-clustering fallback.
    async function computeCurrentEpisodeBoundary(patientData, dates = []) {
        const checkoutIds = extractCheckoutIds(patientData);
        const checkinIds = extractCheckinIds(patientData);
        const allIds = [...checkinIds, ...checkoutIds]; // active admissions first

        let encounters = [];
        if (allIds.length) {
            const checkoutIdSet = new Set(checkoutIds);
            const enc = await limitedMap(allIds, MAX_CONCURRENT_REQUESTS,
                async id => {
                    try {
                        const type = checkoutIdSet.has(id) ? 'checkout' : 'checkin';
                        if (cache.encounters[id]) return cache.encounters[id];
                        const r = await apiFetch(`/api/${type}/${id}`);
                        if (!r.ok) return null;
                        const data = (await r.json()).encounter || null;
                        if (data) cachePut(cache.encounters, id, data);
                        return data;
                    } catch { return null; }
                });
            encounters = enc
                .map((e, i) => e ? { enc: e, id: allIds[i] } : null)
                .filter(Boolean)
                .sort((a, b) => {
                    const da = a.enc.end || a.enc.start || '';
                    const db = b.enc.end || b.enc.start || '';
                    return db > da ? 1 : -1;
                });
        }

        // A checkin's "in-progress" status is a static scrape artifact that
        // never updates once the patient is discharged, so treat a checkin
        // as genuinely active only if it starts after every already-known
        // checkout has already concluded (see displayPatientReport for the
        // full rationale — this replaces that inline computation).
        const latestCheckoutEnd = encounters
            .filter(e => e.enc.status !== 'in-progress')
            .reduce((latest, e) => {
                const end = e.enc.end || e.enc.start || '';
                return end > latest ? end : latest;
            }, '');
        const activeAdm = encounters.find(e =>
            e.enc.status === 'in-progress' &&
            (!latestCheckoutEnd || (e.enc.start || '') > latestCheckoutEnd));
        const lastDischarge = encounters.find(e => e.enc.status !== 'in-progress' && isSubstantiveText(extractEpicrisisText(e.enc)));

        if (activeAdm) {
            return { boundaryDate: activeAdm.enc.start || null, source: 'admission', activeAdm, lastDischarge, encounters };
        }

        if (lastDischarge) {
            // Only trust the discharge as the episode start if no newer
            // imaging/lab activity has drifted more than EPISODE_GAP_DAYS
            // past it — otherwise an old discharge would wrongly pull in
            // everything since as "current" for a patient who's since come
            // back for something unrelated.
            const dischargeDays = isoDateToUTCDays(lastDischarge.enc.end || lastDischarge.enc.start || '');
            const staleRelativeToActivity = dates.some(d => {
                const days = isoDateToUTCDays(d);
                return dischargeDays != null && days != null && (days - dischargeDays) > EPISODE_GAP_DAYS;
            });
            if (!staleRelativeToActivity) {
                return { boundaryDate: lastDischarge.enc.start || null, source: 'discharge', activeAdm, lastDischarge, encounters };
            }
        }

        const clusterStart = clusterEpisodeStart(dates);
        if (clusterStart) {
            return { boundaryDate: clusterStart, source: 'cluster', activeAdm, lastDischarge, encounters };
        }

        return { boundaryDate: null, source: null, activeAdm, lastDischarge, encounters };
    }

    // Memoized wrapper — all call sites (Imaging/Lab grids, Report tab)
    // share one checkin/checkout fetch + boundary computation per patient.
    function getEpisodeBoundary(patientData, dates = []) {
        if (!episodeBoundaryPromise) {
            episodeBoundaryPromise = computeCurrentEpisodeBoundary(patientData, dates);
        }
        return episodeBoundaryPromise;
    }

    const _idList = ids => (ids || []).filter(id => String(id).trim());
    function extractCheckoutIds(patientData) { return _idList(patientData.checkout_ids); }
    function extractCheckinIds(patientData) { return _idList(patientData.checkin_ids); }
    function extractPresentationIds(patientData) { return _idList(patientData.presentation_ids); }

    async function fetchPresentation(id) {
        if (cache.encounters[id]) return cache.encounters[id];
        const response = await apiFetch(`/api/presentation/${id}`);
        // 404 means this presentation simply isn't viewable via this scrape path
        // (e.g. it became an inpatient admission) — a normal empty state, not a failure.
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()).encounter || null;
        if (!data) return null;
        cachePut(cache.encounters, id, data);
        return data;
    }

    // Some scraped epicrisis text repeats a whole paragraph verbatim (e.g. a
    // paste-over during editing at the source, or the same note appearing
    // twice in note[]) — drop exact repeats, keeping the first occurrence,
    // so the model doesn't see (and burn budget on) the same content twice.
    function dedupeParagraphs(text) {
        const seen = new Set();
        return text
            .split(/\n{2,}/)
            .filter(p => {
                const key = p.trim();
                if (!key) return true; // keep blank/whitespace-only segments as-is
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            })
            .join('\n\n');
    }

    function extractEpicrisisText(encounterData) {
        if (!encounterData.notes || !Array.isArray(encounterData.notes)) return '';
        return dedupeParagraphs(encounterData.notes.join('\n\n'));
    }

    // Returns true if text has meaningful content beyond markdown markers and punctuation.
    function isSubstantiveText(text) {
        return /[a-zA-ZÀ-žА-я0-9]/.test(text || '');
    }

    // 72-hour (revised) diagnosis and secondary-diagnosis/comorbidity list from
    // a checkin encounter summary (`working`, `secondary`) — see
    // _encounter_summary() in hippobridge.py.
    function extract72hDiagnosisText(enc) {
        return enc.working || null;
    }
    function extractSecondaryDiagnoses(enc) {
        return enc.secondary || [];
    }

    // Diagnosis + exam-note text for a checkin encounter, used as the display
    // body when there is no epicrisis text yet (ongoing admission — epicrisis
    // is normally only filled in near/at discharge).
    function buildCheckinBody(enc) {
        const parts = [];
        const dx = extractDiagnosisText(enc);
        if (dx) parts.push(dx);
        const dx72h = extract72hDiagnosisText(enc);
        if (dx72h) parts.push(`**72h diagnosis:** ${dx72h}`);
        const secondary = extractSecondaryDiagnoses(enc);
        if (secondary.length) parts.push(`**Secondary diagnoses:** ${secondary.join(', ')}`);
        (enc.notes || []).forEach(text => {
            if (!text) return;
            const clean = text.replace(/^\[Exam general\]\s*/i, '').replace(/^\[Exam local\]\s*/i, '').trim();
            if (clean) parts.push(clean);
        });
        return parts.join('\n\n');
    }

    async function loadAndDisplayEpicrisis(patientData) {
        // Captured before any await: if a slower in-flight call for a previous
        // patient resolves after clearResults() has already moved on to a new
        // one, it must not repopulate epicrisisContent with stale cards (incl.
        // any AI summary) — bail out silently instead of touching the DOM.
        const myGeneration = dataGeneration;
        const checkoutIds = extractCheckoutIds(patientData);
        // Fetch every checkin id, not just ones without a matching checkout id — a
        // genuinely ongoing admission (e.g. ICU, no discharge summary yet) needs its
        // "in-progress" status checked against actual checkout dates, not just id
        // membership (a checkin's status never flips once the patient is discharged).
        const checkinIds = extractCheckinIds(patientData);
        if (checkoutIds.length === 0 && checkinIds.length === 0) {
            if (myGeneration !== dataGeneration) return;
            elements.epicrisisContent.innerHTML = '';
            if (elements.epicrisisNoData) elements.epicrisisNoData.style.display = 'block';
            return;
        }

        const [checkoutEncounters, checkinEncounters] = await Promise.all([
            limitedMap(
                checkoutIds,
                MAX_CONCURRENT_REQUESTS,
                async id => {
                    try { return await fetchEncounterDataForCheckout(id); }
                    catch { return null; }
                }
            ),
            limitedMap(
                checkinIds,
                MAX_CONCURRENT_REQUESTS,
                async id => {
                    try { return await fetchEncounterDataForCheckin(id); }
                    catch { return null; }
                }
            )
        ]);

        // Keep only encounters that have an epicrisis, sorted most-recent-discharge first
        const valid = checkoutEncounters
            .map((enc, i) => enc && extractEpicrisisText(enc) ? { enc, checkoutId: checkoutIds[i], active: false } : null)
            .filter(Boolean)
            .sort((a, b) => {
                const da = a.enc.end || '';
                const db = b.enc.end || '';
                return db > da ? 1 : -1;
            });

        // A checkin's "in-progress" status is a scrape artifact that never updates
        // once the patient is discharged, so treat it as genuinely active only if
        // it starts after every known checkout has already concluded.
        const latestCheckoutEnd = checkoutEncounters
            .filter(Boolean)
            .reduce((latest, enc) => {
                const end = enc.end || enc.start || '';
                return end > latest ? end : latest;
            }, '');
        const activeEnc = checkinEncounters
            .map((enc, i) => enc ? { enc, checkinId: checkinIds[i] } : null)
            .filter(item => item && item.enc.status === 'in-progress' &&
                (!latestCheckoutEnd || (item.enc.start || '') > latestCheckoutEnd))
            .sort((a, b) => (b.enc.start || '').localeCompare(a.enc.start || ''))[0];

        // Ongoing admission always shown first, ahead of past discharges — with
        // diagnosis/exam text as a fallback body when epicrisis hasn't been
        // written yet (it's normally only filled in near/at discharge).
        if (activeEnc) {
            valid.unshift({ enc: activeEnc.enc, checkoutId: activeEnc.checkinId, active: true, fallbackBody: buildCheckinBody(activeEnc.enc) });
        }

        if (myGeneration !== dataGeneration) return;

        if (valid.length === 0) {
            elements.epicrisisContent.innerHTML = '';
            if (elements.epicrisisNoData) elements.epicrisisNoData.style.display = 'block';
            return;
        }

        elements.epicrisisContent.innerHTML = '';

        // Update header eyebrow + meta
        const eyebrowEl = document.getElementById('epicrisisEyebrow');
        const metaEl = document.getElementById('epicrisisMeta');
        const patientNameEl = elements.patientName;
        if (eyebrowEl && patientNameEl?.textContent) {
            eyebrowEl.textContent = `Epicrisis · ${patientNameEl.textContent}`;
        }

        // Accordion cards; combined markdown for Copy button
        let markdown = patientContextHeader(patientData);
        valid.forEach((item, index) => {
            const enc = item.enc;
            // Ongoing admissions rarely have epicrisis text yet (it's normally only
            // written near/at discharge) — fall back to diagnosis + exam notes so the
            // current admission still shows up instead of being silently dropped.
            const epicrisisText = extractEpicrisisText(enc) || item.fallbackBody || '';
            const icd = extractDiagnosisText(enc) || '';
            const admission = enc.start ? formatDate(enc.start) : '';
            const discharge = enc.end ? formatDate(enc.end) : '';
            const service = enc.service || '';
            const ward = enc.wards?.slice(-1)[0] || '';
            const attender = enc.attender || '';

            // Night count (only meaningful once discharged)
            let nights = '';
            if (!item.active && admission && discharge) {
                const ms = new Date(discharge) - new Date(admission);
                const n = Math.round(ms / 86400000);
                nights = `${n} ${n === 1 ? 'night' : 'nights'}`;
            }

            // Markdown
            const meta = [];
            if (admission) meta.push(`**Admission:** ${admission}`);
            if (item.active) meta.push('**Status:** Ongoing');
            else if (discharge) meta.push(`**Discharge:** ${discharge}`);
            if (ward)      meta.push(`**Ward:** ${ward}`);
            if (attender)  meta.push(`**Attending:** ${attender}`);
            if (service)   meta.push(`**Service:** ${service}`);
            const heading = item.active ? `${icd} (Ongoing)` : icd;
            markdown += valid.length === 1 ? `# ${heading}\n\n` : `## ${index + 1}. ${heading}\n\n`;
            if (meta.length) markdown += `${meta.join(' · ')}  \n\n`;
            markdown += epicrisisText.trim() + '\n\n';
            if (index < valid.length - 1) markdown += '---\n\n';

            // Accordion card
            const isOpen = index === 0;
            const card = document.importNode(document.getElementById('epi-card-template').content, true).firstElementChild;
            if (isOpen) card.classList.add('epi-card-open');
            if (item.active) card.classList.add('epi-card-active');
            card.id = `epicrisis-${item.checkoutId}`;
            card.dataset.markdown = `# ${heading}\n\n`
                + (meta.length ? `${meta.join(' · ')}  \n\n` : '')
                + epicrisisText.trim() + '\n';

            const btn    = card.querySelector('.btn-epi-card');
            const body   = card.querySelector('.epi-card-body');
            const chevron = card.querySelector('.epi-chevron');

            btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            btn.title = isOpen ? 'Collapse' : 'Expand for details';
            card.querySelector('.epi-date-range').textContent = item.active ? `${admission} → Present` : `${admission} → ${discharge}`;
            const serviceParts = [ward, attender].filter(Boolean);
            card.querySelector('.epi-service').textContent = serviceParts.length ? serviceParts.join(' · ') : (service || 'Admission');

            const icdBadge = card.querySelector('.epi-icd-badge');
            if (icd) { icdBadge.textContent = icd; } else { icdBadge.remove(); }
            const nightsSpan = card.querySelector('.epi-nights');
            if (item.active) { nightsSpan.textContent = 'Ongoing'; nightsSpan.classList.add('epi-nights-active'); }
            else if (nights) { nightsSpan.textContent = nights; }
            else { nightsSpan.remove(); }
            if (isOpen) chevron.className = 'fas fa-chevron-up epi-chevron';

            body.hidden = !isOpen;
            const copyBtn = card.querySelector('.btn-epi-copy');
            const aiBtn = card.querySelector('.btn-epi-ai');
            if (isSubstantiveText(epicrisisText)) {
                card.querySelector('.epi-prose').innerHTML = marked.parse(epicrisisText.trim());
                copyBtn.addEventListener('click', () => copyMarkdown(card, copyBtn, () => flashIcon(copyBtn)));
                // AI executive summary — inserted inside the collapsible body,
                // above the prose, so it hides/shows with the accordion. Uses
                // the epicrisis text (not the demographics-heavy full markdown).
                wireAiButton(aiBtn, 'epicrisis', () => card.querySelector('.epi-prose'),
                    () => extractEpicrisisText(enc).trim(), { inline: true });
                // Silently redisplay a previously generated summary for this admission, if any.
                runAiSummary(aiBtn, 'epicrisis', () => card.querySelector('.epi-prose'),
                    () => extractEpicrisisText(enc).trim(), { inline: true, auto: true });
            } else {
                const prose = card.querySelector('.epi-prose');
                prose.innerHTML = '<p class="epi-empty">— no content —</p>';
                prose.classList.add('epi-prose-empty');
                card.querySelector('.card-toolbar').hidden = true;
            }

            btn.addEventListener('click', () => {
                const open = card.classList.toggle('epi-card-open');
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
                btn.title = open ? 'Collapse' : 'Expand for details';
                body.hidden = !open;
                chevron.className = `fas fa-chevron-${open ? 'up' : 'down'} epi-chevron`;
            });

            elements.epicrisisContent.appendChild(card);
        });

        if (metaEl) {
            const icdSample = valid[0] ? (extractDiagnosisText(valid[0].enc) || '') : '';
            metaEl.textContent = `${valid.length} ${valid.length === 1 ? 'admission' : 'admissions'}${icdSample ? ' · ' + icdSample : ''}`;
        }

        elements.epicrisisContent.dataset.markdown = markdown;
        if (elements.copyEpicrisisBtn) elements.copyEpicrisisBtn.hidden = !markdown.trim();
    }
    
    const SCHEDULE_STATUS_CLASS = {
        'on-hold':        'status-pending',
        'draft':          'status-sent',
        'active':         'status-active',
        'completed':      'status-done',
        'ended':          'status-ended',
        'revoked':        'status-revoked',
        'entered-in-error': 'status-error',
        'unknown':        'status-pending',
    };

    // Human-readable labels for FHIR request statuses (raw status kept in title)
    const SCHEDULE_STATUS_LABEL = {
        'on-hold':        'Not sent',
        'draft':          'In lab',
        'active':         'In progress',
        'completed':      'Completed',
        'ended':          'Finished',
        'revoked':        'Cancelled',
        'entered-in-error': 'No analyses',
        'unknown':        'Unknown',
    };

    const PAYMENT_TYPE = {
        'ambulator':            { label: 'Outpatient',  cls: 'pay-outpatient' },
        'chitanta':             { label: 'Self-pay',    cls: 'pay-selfpay' },
        'gratuitate':           { label: 'Exempt',      cls: 'pay-exempt' },
        'personal-angajat':     { label: 'Staff',       cls: 'pay-staff' },
        'spitalizare-continua': { label: 'Inpatient',   cls: 'pay-inpatient' },
        'spitalizare-zi':       { label: 'Day case',    cls: 'pay-daycase' },
        'urgenta':              { label: 'Emergency',   cls: 'pay-emergency' },
    };

    let scheduleEntries = [];

    async function showRequestModal(requestId, requestCode, patientName, modality, triggerEl, requesterName, section) {
        const tmpl = document.getElementById('schedule-request-modal-template');
        if (!tmpl) return;
        const modal = tmpl.content.cloneNode(true).querySelector('dialog');

        // Populate identity header immediately from data we already have
        const circleEl = modal.querySelector('.modal-mod-circle');
        const circleAvatar = MODALITY_AVATAR[modality] || { icon: 'fa-question', cls: '' };
        circleEl.innerHTML = modAvatarHTML(modality);
        if (circleAvatar.cls) circleEl.classList.add(circleAvatar.cls);

        modal.querySelector('.modal-type-name').textContent =
            MODALITY_INFO[modality]?.label || 'Report';
        modal.querySelector('.modal-request-code').textContent = requestCode;
        modal.querySelector('.modal-request-id').textContent = `#${requestId}`;
        modal.querySelector('.modal-patient-name').textContent = patientName;

        if (requesterName) {
            modal.querySelector('.modal-requester').textContent = requesterName;
            modal.querySelector('.report-modal-referrer').hidden = false;
        }


        const bodyDiv = modal.querySelector('.report-modal-body');

        // Saved as nodes, not textContent — a trigger built from markup
        // (e.g. the schedule card's summary button, which wraps its text in
        // an <em>) needs that structure restored, not flattened to a plain
        // text node.
        const originalNodes = [...triggerEl.childNodes];
        triggerEl.textContent = '…';
        triggerEl.disabled = true;

        function renderReportContent(report, isImaging) {
            bodyDiv.innerHTML = '';
            bodyDiv.classList.remove('report-empty');
            const forms = report.forms;
            const resultNotes = report.results;

            if (forms.length > 0) {
                const allLab = forms.every(f => f.type === 'lab' || f.reference !== undefined);
                if (allLab) {
                    bodyDiv.appendChild(buildLabTable(forms));
                } else {
                    for (const form of forms) {
                        if (form.title && forms.length > 1) {
                            const h = document.createElement('p');
                            h.className = 'series-result-title';
                            h.textContent = form.title;
                            bodyDiv.appendChild(h);
                        }
                        const div = document.createElement('div');
                        if (form.contentType === 'text/markdown' && form.data) {
                            div.innerHTML = marked.parse(form.data);
                        } else if (form.contentType === 'text/html' && form.data) {
                            div.innerHTML = form.data;
                        } else if (form.data) {
                            const pre = document.createElement('pre');
                            pre.textContent = form.data;
                            div.appendChild(pre);
                        }
                        bodyDiv.appendChild(div);
                    }
                }
            } else if (isImaging && resultNotes.length > 0) {
                // Matches the Imaging tab card's condition (fetchAndFillReport) so a
                // single-investigation report still gets a .series-result-title —
                // refreshActionState's merge pass below matches by title text, and
                // without one here it couldn't tell this investigation was already
                // rendered, appending a duplicate copy underneath.
                resultNotes.forEach(note => {
                    if (!note.text) return;
                    if (note.title) {
                        const titleEl = document.createElement('p');
                        titleEl.className = 'series-result-title';
                        titleEl.textContent = note.title;
                        bodyDiv.appendChild(titleEl);
                    }
                    const div = document.createElement('div');
                    div.className = 'report-note';
                    const normalised = note.text.replace(/\n{2,}/g, '\n');
                    div.innerHTML = marked.parse(normalised).trim();
                    bodyDiv.appendChild(div);
                });
            } else {
                bodyDiv.classList.add('report-empty');
            }
        }

        // Wire up close / load buttons before showing
        modal.querySelectorAll('[data-close-modal], .close').forEach(btn => btn.addEventListener('click', () => modal.close()));
        modal.addEventListener('close', () => document.body.removeChild(modal));
        modal.querySelector('.btn-modal-load-patient').addEventListener('click', () => {
            modal.close();
            loadPatientFromRequest(requestId, patientName, triggerEl);
        });

        bodyDiv.classList.add('report-empty');
        bodyDiv.textContent = 'Loading…';
        document.body.appendChild(modal);
        modal.showModal();

        const imagingTypes = ['radio', 'ct', 'irm', 'eco', 'rads', 'fluoro'];
        const isImaging = imagingTypes.includes(modality);

        // Set by loadAndRenderReport, read by refreshActionState's `performed`
        // calc — mirrors fetchAndFillReport's hasReportFromStudy: once an exam
        // is fully finalised, cerere.asp may stop exposing fn_validate_cerere
        // calls (so allValidated/performed_at both read empty) even though a
        // real report already exists.
        let hasReportFromStudy = false;

        async function loadAndRenderReport() {
            const endpoint = isImaging
                ? `/api/study/${requestId}`
                : `/api/report/${requestId}`;

            const repResp = await apiFetch(endpoint);
            if (repResp.ok) {
                const reportData = reportFromApi(await repResp.json(), isImaging);

                // Date in subtitle
                const date = reportData.date;
                if (date) modal.querySelector('.modal-date').textContent = formatDateWithTime(date);

                // Requester fallback from report data if not passed from schedule row
                if (!requesterName) {
                    const requester = reportData.requester;
                    if (requester) {
                        modal.querySelector('.modal-requester').textContent = requester;
                        modal.querySelector('.report-modal-referrer').hidden = false;
                    }
                }

                // Indication line in header
                const indicationText = reportData.indication;
                if (indicationText) {
                    modal.querySelector('.modal-indication-text').textContent = indicationText;
                    modal.querySelector('.report-modal-indication').hidden = false;
                }
                if (isImaging) {
                    // ImagingStudy's own note (BuletinAnalize.asp's INFO SUPLIMENTAR) is
                    // often empty even when a clinical indication was recorded on the
                    // request itself (Justificare / Situatie clinica on
                    // BuletinSolicitare.asp) — same fallback as the Imaging tab card.
                    // Also the only source for the TRUE ordering physician ("Medic
                    // solicitant") — requesterName passed in from the schedule row
                    // can still be the listing's "Medic curant" (attending
                    // physician) if that row's own lazy correction (scheduleExamObserver)
                    // hadn't resolved yet at the moment this modal was opened.
                    try {
                        const srResp = await apiFetch(`/api/request/${requestId}`);
                        if (srResp.ok) {
                            const srData = (await srResp.json()).request || {};
                            if (!indicationText) {
                                const srIndication = srData.indication || '';
                                if (_isMeaningfulText(srIndication)) {
                                    modal.querySelector('.modal-indication-text').textContent = srIndication;
                                    modal.querySelector('.report-modal-indication').hidden = false;
                                }
                            }
                            const srReferrer = srData.requester;
                            if (_isMeaningfulText(srReferrer)) {
                                modal.querySelector('.modal-requester').textContent = srReferrer;
                                modal.querySelector('.report-modal-referrer').hidden = false;
                            }
                        }
                    } catch (_) { /* best-effort */ }
                }

                // Examiner (reporting physician) appended below content — only
                // when a report actually exists. Without one, performer falls
                // back to the requesting physician server-side, so showing it
                // here would misattribute a report that doesn't exist yet
                // (same guard the Imaging tab cards use, scripts.js:2995-3006).
                const examiner = reportData.examiner;

                renderReportContent(reportData, isImaging);
                const hasReport = !bodyDiv.classList.contains('report-empty');
                hasReportFromStudy = hasReport;

                if (examiner && hasReport) {
                    const signed = document.createElement('p');
                    signed.className = 'report-modal-signed';
                    const signedIcon = document.createElement('i');
                    signedIcon.className = 'fas fa-signature';
                    signedIcon.setAttribute('aria-hidden', 'true');
                    signed.appendChild(signedIcon);
                    signed.append(` ${examiner}`);
                    bodyDiv.appendChild(signed);
                }
            } else if (repResp.status === 404) {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = 'Report not yet available.';
            } else {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = `Could not load report (HTTP ${repResp.status}).`;
            }
        }

        // Report editing/perform/validate: only for users allowed to write
        // reports. Mirrors the Imaging tab's 4-state button logic
        // (fetchAndFillReport), rebuilt here against this modal's own
        // elements instead of an imaging-card article.
        async function refreshActionState() {
            if (!canWriteReports) return;
            // Perform/Cancel/Edit stay visible throughout — only their enabled/
            // disabled state changes below. Disabled by default until the fetch
            // confirms the real state, so nothing is clickable during loading.
            const actionGroupInit = modal.querySelector('.action-group');
            if (actionGroupInit) {
                actionGroupInit.hidden = false;
                actionGroupInit.querySelectorAll('button').forEach(b => { b.disabled = true; });
            }
            const editBtnInit = modal.querySelector('.btn-edit-report');
            if (editBtnInit) { editBtnInit.hidden = false; editBtnInit.disabled = true; }
            try {
                const r = await fetch(`/api/request/${requestId}/patient`, { headers: authHeader() });
                const d = await r.json();
                const analyses = Array.isArray(d.report) ? d.report
                    : (d.report && typeof d.report === 'object' ? [d.report] : []);
                const hasReport    = analyses.some(a => a.text);
                const isEditable   = analyses.some(a => a.editable);
                const allValidated = analyses.length > 0 && analyses.every(a => a.validated);
                // Treat as performed if: DataEfectuarii set, all cerere analyses
                // validated, or the report content already exists (cerere.asp may not
                // expose fn_validate_cerere calls once the exam is fully finalised).
                const performed    = Boolean(d.performed_at) || allValidated || hasReportFromStudy;
                // cerere.asp confirms cancellation itself (see fetchAndFillReport's
                // matching comment above) — d.cancelled is the server-confirmed
                // truth; the local flag (set by the Cancel button handler below,
                // persisting on this modal element across refreshAll() re-renders)
                // is kept only as an optimistic fallback.
                const cancelled = Boolean(d.cancelled) || modal.dataset.cancelled === '1';

                // Ensure every requested investigation is represented (mirrors the
                // Imaging tab card's fetchAndFillReport): match by label against
                // titles already rendered by renderReportContent, and give any
                // investigation without real content yet its own title + "Not yet
                // reported." note, instead of only showing steps with content.
                if (analyses.length) {
                    if (bodyDiv.classList.contains('report-empty')) {
                        bodyDiv.innerHTML = '';
                        bodyDiv.classList.remove('report-empty');
                    }
                    const existingTitles = new Set(
                        [...bodyDiv.querySelectorAll('.series-result-title')]
                            .map(t => (t.firstChild?.textContent ?? '').trim())
                    );
                    const missing = analyses.filter(a => !a.label || !existingTitles.has(a.label.trim()));
                    const showTitles = analyses.length > 1 || analyses[0]?.label;
                    for (const a of missing) {
                        if (showTitles && a.label) {
                            const titleEl = document.createElement('p');
                            titleEl.className = 'series-result-title';
                            titleEl.textContent = a.label;
                            bodyDiv.appendChild(titleEl);
                        }
                        const div = document.createElement('div');
                        if (a.text) {
                            div.className = 'report-note';
                            div.innerHTML = marked.parse(a.text).trim();
                        } else {
                            div.className = 'report-note report-note-pending';
                            div.textContent = 'Not yet reported.';
                        }
                        bodyDiv.appendChild(div);
                    }
                }

                // Perform + Cancel: active until performed or cancelled, then locked
                // (disabled, muted) instead of disappearing — clone-and-replace to
                // drop stale listeners from a previous refresh (same trick
                // fetchAndFillReport uses).
                const actionGroup = modal.querySelector('.action-group');
                if (actionGroup) {
                    const locked = performed || cancelled;
                    let performBtn = actionGroup.querySelector('.btn-perform-exam');
                    if (performBtn) {
                        performBtn.replaceWith(performBtn.cloneNode(true));
                        performBtn = actionGroup.querySelector('.btn-perform-exam');
                        performBtn.disabled = locked;
                        if (!locked) {
                            performBtn.addEventListener('click', () => {
                                markExamPerformedCore(requestId, {
                                    // Lock both buttons while in flight — see the same
                                    // reasoning in markExamPerformed/cancelRequest above.
                                    setDisabled: v => { performBtn.disabled = v; if (cancelBtn) cancelBtn.disabled = v; },
                                    onDone: refreshAll,
                                });
                            });
                        }
                    }
                    let cancelBtn = actionGroup.querySelector('.btn-cancel-request');
                    if (cancelBtn) {
                        cancelBtn.replaceWith(cancelBtn.cloneNode(true));
                        cancelBtn = actionGroup.querySelector('.btn-cancel-request');
                        cancelBtn.disabled = locked;
                        if (!locked) {
                            cancelBtn.addEventListener('click', () => {
                                cancelRequestCore(requestId, {
                                    setDisabled: v => { cancelBtn.disabled = v; if (performBtn) performBtn.disabled = v; },
                                    onDone: () => { modal.dataset.cancelled = '1'; refreshAll(); }
                                });
                            });
                        }
                    }
                }

                // Edit: disabled until performed; once performed, enabled only while
                // there's still an editable, not-fully-validated analysis to write.
                let editBtn = modal.querySelector('.btn-edit-report');
                if (editBtn) {
                    editBtn.replaceWith(editBtn.cloneNode(true));
                    editBtn = modal.querySelector('.btn-edit-report');
                    const editable = performed && isEditable && !allValidated;
                    editBtn.disabled = !editable;
                    if (editable) {
                        editBtn.addEventListener('click', () => {
                            openReportEditorCore(requestId, analyses, { onSaved: refreshAll });
                        });
                    }
                }

                // Validate toggles — one switch per analysis
                const togglesEl = modal.querySelector('.report-modal-validate-toggles');
                if (togglesEl) {
                    togglesEl.replaceChildren();
                    const showToggles = performed && hasReport && analyses.length > 0;
                    togglesEl.hidden = !showToggles;
                    if (showToggles) {
                        for (const analysis of analyses) {
                            const inp = document.createElement('input');
                            inp.type = 'checkbox';
                            inp.checked = analysis.validated;
                            inp.setAttribute('aria-label', `Validated: ${analysis.label}`);
                            const slider = document.createElement('span');
                            slider.className = 'switch-slider';
                            const lbl = document.createElement('label');
                            lbl.className = 'switch';
                            lbl.append(inp, slider);

                            const fmtLabel = (checked) => {
                                const status = checked ? 'Valid' : 'Invalid';
                                return analyses.length > 1 ? `${analysis.label}: ${status}` : status;
                            };
                            const labelText = document.createElement('span');
                            labelText.className = 'switch-label';
                            labelText.textContent = fmtLabel(analysis.validated);

                            inp.addEventListener('change', () => {
                                labelText.textContent = fmtLabel(inp.checked);
                                setValidatedCore(requestId, analysis.anl_id, analysis.id_grup, inp.checked, {
                                    onDone: refreshAll
                                });
                            });

                            const row = document.createElement('div');
                            row.className = 'validate-row';
                            row.append(lbl, labelText);
                            togglesEl.appendChild(row);
                        }
                    }
                }
            } catch (_) { /* silent — same defensive pattern as fetchAndFillReport's cerere fetch */ }
        }

        async function refreshAll() {
            try {
                await loadAndRenderReport();
            } catch (err) {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = err.message;
            }
            await refreshActionState();
        }

        await whoamiReady;
        await refreshAll();
        triggerEl.replaceChildren(...originalNodes);
        triggerEl.disabled = false;
    }

    async function loadPatientFromRequest(requestId, patientName, triggerEl) {
        if (!requestId) {
            if (!patientName) return;
            elements.cnpInput.value = patientName;
            elements.form.dispatchEvent(new Event('submit'));
            return;
        }
        const originalText = triggerEl.textContent;
        triggerEl.textContent = '…';
        triggerEl.disabled = true;
        try {
            const resp = await apiFetch(`/api/study/${requestId}?justification=0`);
            if (resp.ok) {
                const json = await resp.json();
                const patientId = json.patient?.id || null;
                if (patientId) {
                    elements.cnpInput.value = patientId;
                    triggerEl.textContent = originalText;
                    triggerEl.disabled = false;
                    elements.form.dispatchEvent(new Event('submit'));
                    return;
                }
            }
        } catch (_) { /* fall through */ }
        // Fallback: search by name
        if (!patientName) { triggerEl.textContent = originalText; triggerEl.disabled = false; return; }
        elements.cnpInput.value = patientName;
        elements.form.dispatchEvent(new Event('submit'));
        triggerEl.textContent = originalText;
        triggerEl.disabled = false;
    }

    function fetchScheduleFromInputs(force = false) {
        const start       = elements.scheduleStartDate?.value || null;
        const end         = elements.scheduleEndDate?.value || null;
        const patientText = elements.schedulePatientFilter?.value.trim() || null;
        const labId       = elements.scheduleLabFilter?.value || null;
        const sectionName = elements.scheduleSectionFilter?.value || null;
        const status      = activeScheduleStatusFilter.size ? [...activeScheduleStatusFilter].join(',') : null;
        const limit       = elements.scheduleLimitSelect?.value || null;
        fetchSchedule(start, end, force, patientText, labId, sectionName, status, limit);
        updateScheduleClearFiltersVisibility();
    }

    async function fetchSchedule(startDate, endDate, force = false, patientText = null, labId = null, sectionName = null, status = null, limit = null) {
        if (!elements.scheduleBody) return;
        // An open exam list stays visible during a refresh and is rebuilt
        // in place from the new entries.
        const listOpen = !!elements.scheduleMdPanel && !elements.scheduleMdPanel.hidden;
        if (force) _mdPatientLists.clear(); // a refresh may bring new exams
        const params = new URLSearchParams();
        if (startDate)   params.set('start_date', startDate);
        if (endDate)     params.set('end_date', endDate);
        if (force)       params.set('refresh', '1');
        if (patientText) params.set('patient_text', patientText);
        if (labId)       params.set('lab_id', labId);
        if (sectionName) params.set('section_name', sectionName);
        if (status)      params.set('status', status);
        if (limit)       params.set('limit', limit);
        const url = `/api/schedule${params.toString() ? '?' + params.toString() : ''}`;
        if (elements.noSchedule) elements.noSchedule.style.display = 'none';
        showLoading('Loading schedule…');
        try {
            const resp = await apiFetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const bundle = await resp.json();
            scheduleEntries = bundle.requests || [];
            // Repopulate section dropdown only when not currently filtered by section
            if (!sectionName) populateSectionFilter(scheduleEntries);
            renderSchedule();
            if (elements.scheduleTable) elements.scheduleTable.dataset.loaded = '1';
            startSchedulePrefetch(scheduleEntries);
            if (listOpen) buildScheduleMarkdown(true);
        } catch (err) {
            showToast(`Failed to load schedule: ${err.message}`, 'error');
        } finally {
            hideLoading();
        }
    }

    // PACS study-check (see pacs.py): a secondary, independent signal from
    // Hipocrate's own performed_at — surfaced as a small checkmark badge on
    // the modality avatar rather than a new pill, so it doesn't compete with
    // the primary status. Lazy, per-row/card via GET /api/pacs/<id> (a pure
    // in-memory lookup, no PACS I/O) instead of shipping the whole
    // in-memory table on every schedule/imaging load — see
    // pacsStatusObserver below, which triggers one fetch per element as it
    // scrolls into view, same pattern as scheduleExamObserver. Failures are
    // non-critical (silent): this is best-effort/supplementary, never the
    // primary status source.
    async function triggerPacsRefresh() {
        try { await apiFetch('/api/pacs/refresh', { method: 'POST' }); }
        catch (err) { /* best-effort; ignore */ }
    }

    function wardFamily(section) {
        // First word of the ward name; must match HippoClientSchedule._ward_family.
        return section.trim().split(/\s+/)[0];
    }

    function populateSectionFilter(entries) {
        if (!elements.scheduleSectionFilter) return;
        const sections = [...new Set(entries.map(r => r.section || '').filter(Boolean))].sort();
        const current = elements.scheduleSectionFilter.value;
        elements.scheduleSectionFilter.innerHTML = '<option value="">All wards</option>';

        // Group sections by family name to synthesize combined entries.
        const familyMap = new Map(); // family -> Set of real sections
        sections.forEach(s => {
            const family = wardFamily(s);
            if (!familyMap.has(family)) {
                familyMap.set(family, new Set());
            }
            familyMap.get(family).add(s);
        });

        // Build final option list: real sections + synthetic family entries
        // (where family has 2+ members and the family name itself is not already real).
        const optionValues = new Set();
        const toRender = [];

        sections.forEach(s => {
            optionValues.add(s);
            toRender.push(s);
        });

        // Add synthetic family entries where needed.
        familyMap.forEach((members, family) => {
            if (members.size >= 2 && !optionValues.has(family)) {
                toRender.push(family);
            }
        });

        // Sort the final list and render.
        toRender.sort().forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            if (s === current) opt.selected = true;
            elements.scheduleSectionFilter.appendChild(opt);
        });
    }

    // ── On-demand markdown list of the displayed schedule exams ──
    // Built only when the "Exam list" button is clicked: per row, cerere
    // (sex/age/diagnosis/patient id), the request form (indication), and the
    // patient's last earlier exam of the same modality with its report text.
    function hideScheduleMarkdown() {
        scheduleMdRun++;
        if (elements.scheduleMdPanel) {
            elements.scheduleMdPanel.hidden = true;
            elements.scheduleMdPanel.dataset.markdown = '';
        }
    }

    const _mdModalityGroup = m => (m === 'fluoro' ? 'rads' : m);
    const _mdIso = s => (s || '').replace('T', ' ').slice(0, 16);

    function _mdReportText(study) {
        return (study.studies || []).map(s => (s.result || '').trim()).filter(Boolean).join('\n\n');
    }

    // Best clinical indication for a request, resolved server-side by
    // /api/request/{id} (resolve_clinical_indication over BuletinSolicitare).
    function _mdSolicitareIndication(sr) {
        return sr?.request?.indication || '';
    }

    async function _mdJson(url) {
        const r = await apiFetch(url);
        return r.ok ? r.json() : null;
    }

    // Modalities with their own Hipocrate domain: /api/request?type= then makes
    // one upstream call instead of fetching every imaging and lab domain.
    const _mdTypedModalities = new Set(['radio', 'ct', 'irm', 'eco', 'rads']);
    const _mdPatientLists = new Map();
    function _mdPatientList(pid, modality) {
        const type = _mdTypedModalities.has(modality) ? modality : '';
        const key = `${pid}|${type}`;
        if (!_mdPatientLists.has(key)) {
            _mdPatientLists.set(key, _mdJson(`/api/request?patient=${encodeURIComponent(pid)}`
                + (type ? `&type=${type}` : ''))
                .then(b => b?.requests || []).catch(() => []));
        }
        return _mdPatientLists.get(key);
    }

    // Newest earlier exam of the same modality that actually has report text
    // (exams without one, e.g. partial/unwritten reports, are skipped), with
    // its cached AI summary when the server has one. Shared by the exam list
    // and the schedule cards. Returns {date, region, text, summary} or null.
    async function _findPreviousExam(requestId, dateTime, modality, patientId) {
        const list = await _mdPatientList(patientId, modality);
        const cur = _mdIso(dateTime);
        const candidates = list
            .filter(e => e.id !== requestId
                && _mdModalityGroup(e.type) === modality
                && _mdIso(e.date_time) < cur)
            .sort((a, b) => _mdIso(b.date_time).localeCompare(_mdIso(a.date_time)))
            .slice(0, 5);
        for (const c of candidates) {
            const study = await _mdJson(`/api/study/${c.id}?justification=0`);
            const text = study ? _mdReportText(study) : '';
            if (!text) continue;
            return { id: c.id, code: c.barcode || '', date: _mdIso(c.date_time),
                     region: (c.regions || []).filter(Boolean).join(', '), text,
                     summary: study.summary || '' };
        }
        return null;
    }

    async function _mdRowData(r) {
        const out = { name: r.patient_name || '', ward: r.section || '',
                      modalityLabel: r.laboratory || '', sex: '', age: '', diagnosis: '',
                      indication: '', prev: null, failed: false };
        const modality = _mdModalityGroup(r.modality || '');
        try {
            const cached = _examCache[r.request_id];
            // One request: the order form plus (when cerere.asp is readable)
            // patient.id and the recent-requests strip.
            const sr = await _mdJson(`/api/request/${r.request_id}`);
            const p = { ...(sr?.patient || {}) }, rq = sr?.request || {};
            if (!p.id && p.cnp) {
                // cerere.asp is denied for labs the user can't open (e.g. CT),
                // so no patient id came back: find it by CNP.
                const found = await _mdJson(`/api/patient?q=${encodeURIComponent(p.cnp)}`);
                p.id = found?.patient?.id;
            }
            out.sex = p.gender || '';
            out.age = String(p.age || '').replace(/\D+$/, '');
            out.diagnosis = [rq.clinical_situation, rq.diagnosis_referral].find(_isMeaningfulText) || '';
            const ind = cached ? cached.indication : _mdSolicitareIndication(sr);
            out.indication = _isMeaningfulText(ind) ? ind : '';
            // The recent-requests strip: if it lists only this request, treat
            // as a first-time patient and skip the full history lookup.
            const strip = rq.previous;
            const firstTime = Array.isArray(strip) && strip.length === 1
                && String(strip[0].id) === String(r.request_id);
            if (p.id && modality && !firstTime) {
                out.prev = await _findPreviousExam(r.request_id, r.date_time, modality, p.id);
            }
        } catch (_) { out.failed = true; }
        return out;
    }

    function _mdFallbackRow(r) {
        return { name: r.patient_name || '', ward: r.section || '',
                 modalityLabel: r.laboratory || '', sex: '', age: '', diagnosis: '',
                 indication: '', prev: null, failed: true };
    }

    // Presentation-neutral view of one row, shared by the markdown and DOM
    // renderers so both always show the same fields.
    function _mdView(d) {
        const who = [d.sex, d.age && `${d.age} y`].filter(Boolean).join(', ');
        const fields = [];
        if (d.diagnosis) fields.push(['Diagnosis', d.diagnosis]);
        if (d.indication && d.indication.trim().toLowerCase() !== d.diagnosis.trim().toLowerCase()) {
            fields.push(['Indication', d.indication]);
        }
        return {
            name: d.name || '(unnamed)',
            who,
            meta: [d.ward, d.modalityLabel].filter(Boolean).join(' · '),
            fields,
            prevLabel: `Previous ${d.modalityLabel}`,
            prevWhen: d.prev ? [d.prev.date, d.prev.region].filter(Boolean).join(' · ') : '',
            prevText: d.prev?.text || '',
            prevSummary: d.prev?.summary || '',
            showPrev: !!d.prev,
        };
    }

    function _mdEntryMarkdown(d) {
        const v = _mdView(d);
        const lines = [`### ${v.name}${v.who ? ` _${v.who}_` : ''}`];
        if (v.meta) lines.push(`_${v.meta}_`);
        lines.push('');
        v.fields.forEach(([k, val]) => lines.push(`**${k}:** ${val}`));
        if (d.failed) lines.push('_(details unavailable)_');
        if (v.showPrev) {
            lines.push(`**${v.prevLabel}:** ${v.prevWhen}`);
            if (v.prevSummary) lines.push(`**AI summary:** ${v.prevSummary}`);
            else if (v.prevText) lines.push('', v.prevText.split('\n').map(l => '> ' + l).join('\n'));
        }
        return lines.join('\n');
    }

    function _mdEntryEl(d) {
        const v = _mdView(d);
        const el = (tag, cls, text) => {
            const n = document.createElement(tag);
            if (cls) n.className = cls;
            if (text != null) n.textContent = text;
            return n;
        };
        const art = el('article', 'exam-entry');
        const head = el('header', 'exam-entry-head');
        const h = el('h3', 'exam-name', v.name);
        if (v.who) h.append(el('span', 'exam-who', v.who));
        head.append(h);
        if (v.meta) head.append(el('p', 'exam-meta', v.meta));
        art.append(head);

        if (v.fields.length) {
            const dl = el('dl', 'exam-fields');
            v.fields.forEach(([k, val]) => dl.append(el('dt', null, k), el('dd', null, val)));
            art.append(dl);
        }
        if (d.failed) art.append(el('p', 'exam-note', 'Details unavailable'));

        if (v.showPrev) {
            const prev = el('section', 'exam-prev');
            const ph = el('div', 'exam-prev-head');
            ph.append(el('span', 'exam-prev-label', v.prevLabel));
            if (v.prevWhen) ph.append(el('span', 'exam-prev-when', v.prevWhen));
            prev.append(ph);
            if (v.prevSummary) {
                ph.append(el('span', 'exam-ai-tag', 'AI summary'));
                prev.append(el('div', 'exam-prev-text exam-prev-ai', v.prevSummary));
            } else {
                const body = el('div', 'exam-prev-text');
                body.innerHTML = marked.parse(v.prevText.replace(/\n{2,}/g, '\n'));
                prev.append(body);
            }
            art.append(prev);
        }
        return art;
    }

    function _mdSubtitle(count) {
        const ward = elements.scheduleSectionFilter?.value || '';
        const lab = elements.scheduleLabFilter;
        const modality = lab?.value ? lab.options[lab.selectedIndex].text : '';
        const from = elements.scheduleStartDate?.value || '', to = elements.scheduleEndDate?.value || '';
        const period = from && to && from !== to ? `${from} – ${to}` : (from || to);
        return [
            `${count} exam${count !== 1 ? 's' : ''}`,
            ward && `Ward: ${ward}`,
            modality && `Modality: ${modality}`,
            period && `Period: ${period}`,
            `Generated ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`,
        ].filter(Boolean).join(' · ');
    }

    function _mdRefreshMarkdown() {
        elements.scheduleMdPanel.dataset.markdown =
            `# Exam list\n\n_${scheduleMdState.subtitle}_\n\n` +
            scheduleMdState.rows.map(_mdEntryMarkdown).join('\n\n---\n\n');
    }

    // Replaces each previous-exam report with its AI summary, one request at
    // a time, reusing the "imaging" prompt (server-cached per report text).
    function _mdApplySummary(i, summary) {
        const { rows, els } = scheduleMdState;
        rows[i].prev.summary = summary;
        const fresh = _mdEntryEl(rows[i]);
        els[i].replaceWith(fresh);
        els[i] = fresh;
    }

    // Fills in summaries the server already has cached (check_only: no LLM
    // call, null when absent) so a rebuilt list keeps its AI summaries.
    async function _mdApplyCachedSummaries(run) {
        const { rows } = scheduleMdState;
        const idx = rows.map((d, i) => i).filter(i => rows[i].prev?.text && !rows[i].prev.summary);
        await limitedMap(idx, 4, async i => {
            const summary = await aiSummarize('imaging', rows[i].prev.text, { checkOnly: true });
            if (summary && run === scheduleMdRun) _mdApplySummary(i, summary);
        });
        if (run === scheduleMdRun) _mdRefreshMarkdown();
    }

    async function summarizeScheduleMdReports() {
        const { rows, els } = scheduleMdState;
        const todo = rows.map((d, i) => i).filter(i => rows[i].prev?.text && !rows[i].prev.summary);
        if (!todo.length) { showToast('No previous reports to summarize', 'warning'); return; }
        const run = scheduleMdRun;
        const btn = elements.scheduleMdAiBtn;
        const label = btn.querySelector('span');
        const orig = label.textContent;
        btn.disabled = true;
        let n = 0, failed = 0;
        try {
            for (const i of todo) {
                if (run !== scheduleMdRun) return;
                label.textContent = `${++n}/${todo.length}`;
                try {
                    const summary = await aiSummarize('imaging', rows[i].prev.text);
                    if (run !== scheduleMdRun) return;
                    if (summary) _mdApplySummary(i, summary);
                } catch (err) {
                    failed++;
                }
            }
            _mdRefreshMarkdown();
            if (failed) showToast(`${failed} summar${failed === 1 ? 'y' : 'ies'} failed`, 'warning');
        } finally {
            label.textContent = orig;
            btn.disabled = false;
        }
    }

    // silent: rebuild after a schedule refresh — no loading overlay or scroll,
    // and the current list stays until the new one is ready.
    async function buildScheduleMarkdown(silent = false) {
        const entries = scheduleEntries.slice();
        if (!entries.length) {
            if (silent) hideScheduleMarkdown();
            else showToast('No schedule entries to list', 'warning');
            return;
        }
        const run = ++scheduleMdRun;
        const btn = elements.scheduleMdBtn;
        btn.disabled = true;
        _mdPatientLists.clear();
        let done = 0;
        if (!silent) showLoading('Building exam list…');
        try {
            const results = await limitedMap(entries, 4, async r => {
                const d = await _mdRowData(r);
                if (run === scheduleMdRun && !silent) setLoadingStep(`${++done}/${entries.length}`);
                return d;
            });
            if (run !== scheduleMdRun) return;
            const rows = results.map((d, i) => d || _mdFallbackRow(entries[i]));
            rows.sort((x, y) => (x.name || '').localeCompare(y.name || '', undefined, { sensitivity: 'base' }));
            const subtitle = _mdSubtitle(rows.length);
            scheduleMdState.subtitle = subtitle;
            scheduleMdState.rows = rows;
            scheduleMdState.els = rows.map(_mdEntryEl);
            elements.scheduleMdBody.replaceChildren(...scheduleMdState.els);
            elements.scheduleMdSub.textContent = subtitle;
            _mdRefreshMarkdown();
            elements.scheduleMdPanel.hidden = false;
            if (!silent) elements.scheduleMdPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            _mdApplyCachedSummaries(run).catch(() => {});
        } catch (err) {
            showToast(`Failed to build exam list: ${err.message}`, 'error');
        } finally {
            if (!silent) hideLoading();
            btn.disabled = false;
        }
    }

    function isScheduleFilterActive() {
        return !!(
            (elements.schedulePatientFilter?.value.trim()) ||
            (elements.scheduleLabFilter?.value) ||
            (elements.scheduleSectionFilter?.value) ||
            activeScheduleStatusFilter.size
        );
    }

    function updateScheduleClearFiltersVisibility() {
        if (!elements.scheduleClearFiltersBtn) return;
        elements.scheduleClearFiltersBtn.hidden = !isScheduleFilterActive();
    }

    function clearScheduleFilters() {
        if (elements.schedulePatientFilter) elements.schedulePatientFilter.value = '';
        if (elements.scheduleLabFilter) elements.scheduleLabFilter.value = '';
        if (elements.scheduleSectionFilter) elements.scheduleSectionFilter.value = '';
        activeScheduleStatusFilter.clear();
        elements.scheduleStatusChips?.querySelectorAll('.chip').forEach(c => {
            const isAll = c.dataset.status === '';
            c.classList.toggle('chip-active', isAll);
            c.setAttribute('aria-pressed', String(isAll));
        });
        fetchScheduleFromInputs();
    }

    function renderSchedule() {
        const container = elements.scheduleTimeline || elements.scheduleBody;
        if (!container) return;

        container.innerHTML = '';

        // Status filtering happens server-side now (see fetchScheduleFromInputs);
        // scheduleEntries already reflects the active status filter.
        const visibleEntries = scheduleEntries;

        if (scheduleEntries.length === 0) {
            if (elements.scheduleTable) elements.scheduleTable.hidden = true;
            if (elements.scheduleTimeline) elements.scheduleTimeline.hidden = true;
            if (elements.noSchedule) elements.noSchedule.style.display = '';
            if (elements.scheduleModBars) elements.scheduleModBars.hidden = true;
            return;
        }

        if (visibleEntries.length === 0) {
            if (elements.scheduleTimeline) elements.scheduleTimeline.hidden = true;
            if (elements.noSchedule) elements.noSchedule.style.display = '';
            if (elements.scheduleModBars) elements.scheduleModBars.hidden = true;
            return;
        }

        if (elements.noSchedule) elements.noSchedule.style.display = 'none';
        if (elements.scheduleTimeline) elements.scheduleTimeline.hidden = false;

        // Render hero metrics + mod bars
        renderScheduleHero();

        const isMultiDay = (elements.scheduleStartDate?.value || '') !== (elements.scheduleEndDate?.value || '');
        let currentDay = null;

        visibleEntries.forEach((r, idx) => {
            const authoredOn = r.date_time || '';
            const hasTime = authoredOn.includes(' ');
            const day = hasTime ? authoredOn.split(' ')[0] : authoredOn;
            const time = hasTime ? authoredOn.split(' ')[1] : '';
            const isLast = idx === visibleEntries.length - 1;

            // Day group heading
            if (isMultiDay && day && day !== currentDay) {
                currentDay = day;
                const heading = document.createElement('p');
                heading.className = 'timeline-day-heading';
                heading.textContent = formatDayHeading(day);
                container.appendChild(heading);
            }

            const timeLabel = isMultiDay ? (time || day) : (time || authoredOn);
            container.appendChild(buildTimelineRow(r, { isLast, timeLabel }));
        });

        if (elements.scheduleTable) elements.scheduleTable.hidden = false;
    }

    // Builds one schedule timeline row.
    function buildTimelineRow(r, { isLast, timeLabel }) {
        const authoredOn = r.date_time || '';
        const patientName = r.patient_name || '';
        const requestCode = r.request_code || r.request_id || '';
        const section = r.section || '';
        const requestedBy = r.requested_by || '';
        const laboratory = r.laboratory || '';
        const modalitySlug  = r.modality || '';
        const paymentSlug   = r.payment_code || '';
        const status = r.status_code || '';
        const statusClass = SCHEDULE_STATUS_CLASS[status] || '';
        const isUrgent = r.priority_code === 'urgent';
        const avatar = MODALITY_AVATAR[modalitySlug] || { icon: 'fa-question', cls: '' };

        // Row: time col + card
        const row = document.importNode(document.getElementById('timeline-row-template').content, true).firstElementChild;
        if (modalitySlug) row.dataset.modality = modalitySlug;

        // Time column
        const timeEl = row.querySelector('.timeline-time');
        timeEl.dateTime = authoredOn.replace(' ', 'T');
        timeEl.textContent = timeLabel;

        const dot = row.querySelector('.timeline-dot');
        if (avatar.cls) dot.classList.add(avatar.cls);
        if (isLast) row.querySelector('.timeline-line').remove();

        // Card
        const card = row.querySelector('.timeline-card');
        if (isUrgent) card.classList.add('urgent-ring');

        const avatarEl = row.querySelector('.timeline-mod-avatar');
        if (avatar.cls) avatarEl.classList.add(avatar.cls);
        // Preserve the PACS-confirmed badge (in the template markup) across
        // this innerHTML overwrite — it starts hidden and is only revealed
        // once pacsStatusObserver's lazy per-row check resolves.
        const pacsBadge = avatarEl.querySelector('.pacs-confirmed-badge');
        avatarEl.innerHTML = modAvatarHTML(modalitySlug);
        if (pacsBadge) {
            avatarEl.appendChild(pacsBadge);
            pacsBadge.dataset.requestId = r.request_id;
            pacsStatusObserver.observe(avatarEl);
        }
        avatarEl.title = MODALITY_INFO[modalitySlug]?.label || laboratory || modalitySlug;

        const nameBtn = row.querySelector('.timeline-card-patient');
        nameBtn.textContent = patientName;
        nameBtn.title = `Load patient record for ${patientName}`;
        nameBtn.addEventListener('click', () => loadPatientFromRequest(r.request_id, patientName, nameBtn));

        const urgBadge = row.querySelector('.urgent-badge');
        if (isUrgent) { urgBadge.hidden = false; } else { urgBadge.remove(); }

        const payInfo = PAYMENT_TYPE[paymentSlug];
        const payBadge = row.querySelector('.timeline-pay-badge');
        // Two separators now carry .timeline-pay-sep (one just spaces the
        // code from the numeric id; the other gates the pay badge) — grab
        // the one actually adjacent to the badge, not the first match.
        const paySep   = payBadge?.previousElementSibling;
        if (payInfo) {
            payBadge.textContent = payInfo.label;
            if (payInfo.cls) payBadge.classList.add(payInfo.cls);
            payBadge.hidden = false;
        } else {
            payBadge.remove();
            paySep?.remove();
        }

        const regionLine = row.querySelector('.timeline-card-region');
        regionLine.textContent = laboratory;
        regionLine.dataset.requestId = r.request_id;
        regionLine.dataset.modality = laboratory;
        regionLine.dataset.section = section || '';

        // Meta line: hide unused parts
        const metaSectionEl  = row.querySelector('.timeline-meta-section');
        const metaRequesterEl = row.querySelector('.timeline-meta-requester');
        const seps = row.querySelectorAll('.timeline-meta-sep');
        if (section) {
            metaSectionEl.querySelector('span').textContent = section;
            regionLine._sectionEl = metaSectionEl;
        } else {
            metaSectionEl.remove();
            seps[0]?.remove();
        }
        // Schedule rows now carry a requester straight from the "Cerut de"
        // column (restored 2026-08-14) — but that's Medic curant (the
        // attending physician), same as cerere.asp's own field. Show it
        // immediately so there's no blank/hidden flash, but still stash the
        // element refs unconditionally: the lazy BuletinSolicitare.asp fetch
        // below is the only source for Medic solicitant (the true orderer,
        // which differs from Medic curant whenever the patient's regular
        // doctor isn't the one who placed this specific order) and should
        // still overwrite this value with the more accurate one once it
        // resolves.
        if (requestedBy) {
            metaRequesterEl.querySelector('span').textContent = requestedBy;
        } else {
            metaRequesterEl.hidden = true;
            if (seps[1]) seps[1].hidden = true;
        }
        regionLine._requesterEl = metaRequesterEl;
        regionLine._requesterSep = seps[1] || null;
        regionLine._nameBtn = nameBtn;
        regionLine._patientName = patientName;
        regionLine._prevLine = row.querySelector('.timeline-card-prev');
        regionLine._req = r;

        // Analysis count ("Numar analize") — available immediately from the
        // same listing fetch as everything else above (no lazy fetch needed
        // for this one, unlike region/indication/true-orderer). Only shown
        // above 1: most requests carry a single analysis, so a "1" badge on
        // every row would be noise rather than signal.
        const metaCountEl = row.querySelector('.timeline-meta-count');
        const analysisCount = r.analysis_count;
        if (analysisCount && analysisCount > 1) {
            metaCountEl.querySelector('span').textContent = `${analysisCount} analyses`;
            metaCountEl.hidden = false;
        } else {
            metaCountEl.remove();
            seps[2]?.remove();
        }

        const codeBtn = row.querySelector('.timeline-code');
        codeBtn.textContent = requestCode;
        codeBtn.title = `View request details (${requestCode})`;
        codeBtn.addEventListener('click', () => showRequestModal(r.request_id, requestCode, patientName, modalitySlug, codeBtn, requestedBy, section));
        const numericIdEl = row.querySelector('.timeline-numeric-id');
        if (hipocrateUrl) {
            const idLink = document.createElement('a');
            idLink.href = `${hipocrateUrl}/PARA/NOM/Listare/cerere.asp?id=${r.request_id}`;
            idLink.target = '_blank';
            idLink.rel = 'noopener noreferrer';
            idLink.textContent = `#${r.request_id}`;
            numericIdEl.appendChild(idLink);
        } else {
            numericIdEl.textContent = `#${r.request_id}`;
        }

        const statusBadge = row.querySelector('.timeline-status-badge');
        if (statusClass) statusBadge.classList.add(statusClass);
        statusBadge.textContent = SCHEDULE_STATUS_LABEL[status] || status;
        statusBadge.title = status;

        scheduleExamObserver.observe(regionLine);
        return row;
    }

    // Filters placeholder junk like ". .. ." that doctors sometimes type just to pass form validation
    function _isMeaningfulText(text) {
        return !!text && /[A-Za-z0-9À-ɏ]/.test(text);
    }

    // Intersection observer: one lazy fetch per row (BuletinSolicitare.asp, the
    // request/order form) when it scrolls into view. It's the only page that
    // reliably has all three: region, indication, AND the true ordering
    // physician ("Medic solicitant") — cerere.asp's strMedicId only ever gives
    // the attending physician ("Medic curant"), which differs from the orderer
    // whenever the patient's regular doctor isn't the one who placed this order.
    const _examCache = {};
    const scheduleExamObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const el = entry.target;
            scheduleExamObserver.unobserve(el);
            const id = el.dataset.requestId;
            if (!id) return;
            if (_examCache[id]) {
                _applyExamLabel(el, _examCache[id]);
                if (_examCache[id].referrer) _applyReferrer(el, _examCache[id].referrer);
                if (_examCache[id].age) _applyPatientAge(el, _examCache[id].age);
                if (_examCache[id].triage) _applyTriage(el, _examCache[id].triage);
                _showCardLine(el, _examCache[id]);
                return;
            }
            const examPromise = apiFetch(`/api/request/${id}`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    const rq = data?.request || {};
                    const regions = rq.region ? [rq.region] : [];
                    const indication = _isMeaningfulText(rq.indication) ? rq.indication : '';
                    const referrer = rq.requester || '';
                    const age = data?.patient?.age || '';
                    // Worth looking for a previous exam only when the recent-
                    // requests strip lists something besides this request.
                    const strip = rq.previous;
                    const hasPrev = Array.isArray(strip) && strip.some(e => String(e.id) !== String(id));
                    return { regions, indication, referrer, age, patientId: data?.patient?.id || '', hasPrev };
                })
                .catch(() => ({ regions: [], indication: '', referrer: '', age: '' }));

            // UPU (ER department) rows also get their triage level looked up
            // (FUPU.asp, via /api/request/{id}/triage — server-side because
            // it needs a patient lookup + presentation id first). Section is
            // a more reliable ER signal than the payment-type badge (an ER
            // patient can still be billed under a non-Urgenta payment type).
            // Skipped for non-UPU rows to avoid a wasted round trip.
            const triagePromise = (el.dataset.section || '').toUpperCase() === 'UPU'
                ? apiFetch(`/api/request/${id}/triage`)
                    .then(r => r.ok ? r.json() : null)
                    .then(data => data?.triage_priority || '')
                    .catch(() => '')
                : Promise.resolve('');

            Promise.all([examPromise, triagePromise]).then(([cached, triage]) => {
                cached.triage = triage;
                _examCache[id] = cached;
                _applyExamLabel(el, cached);
                if (cached.referrer) _applyReferrer(el, cached.referrer);
                if (cached.age) _applyPatientAge(el, cached.age);
                if (triage) _applyTriage(el, triage);
                _showCardLine(el, cached);
            });
        });
    }, { rootMargin: '200px' });

    // ── Previous exam (same modality) on the schedule card ──
    // Looked up lazily per row, after the row's own request fetch tells us the
    // patient and that earlier requests exist. Imaging modalities only (the
    // lab list isn't type-filterable), two lookups in flight at a time.
    const _prevQueue = [];
    let _prevActive = 0;
    function _enqueuePrev(task) {
        _prevQueue.push(task);
        (function pump() {
            while (_prevActive < 2 && _prevQueue.length) {
                const next = _prevQueue.shift();
                _prevActive++;
                next().finally(() => { _prevActive--; pump(); });
            }
        })();
    }

    // The previous exam matters while the request is still in flight; once it
    // is finished (completed/ended) there is no special need for it.
    const _PREV_FINISHED_STATUSES = new Set(['completed', 'ended']);
    function _prevRelevant(req) {
        return !_PREV_FINISHED_STATUSES.has(req?.status_code);
    }

    // Fourth card line: the previous same-modality exam while the request is
    // in flight, the request's own report once it is finished. Looked up once
    // per row (prevChecked / ownChecked), then just re-shown on redraws.
    function _showCardLine(el, cached) {
        const key = _prevRelevant(el._req) ? 'prev' : 'own';
        if (!cached[key + 'Checked']) {
            (key === 'prev' ? _loadPrevLine : _loadOwnLine)(el, cached);
            return;
        }
        const v = cached[key];
        // A summary still being generated for a row that was redrawn: follow
        // the same job so this new element updates too.
        if (v?.pending) _autoSummarizePrev(v, () => _applyPrevLine(el, v));
        _applyPrevLine(el, v);
    }

    // Finished request: its own report's AI summary (cached one, else queued)
    function _loadOwnLine(el, cached) {
        const req = el._req;
        cached.ownChecked = true;
        if (!_mdTypedModalities.has(_mdModalityGroup(req?.modality || ''))) return;
        _enqueuePrev(async () => {
            try {
                const study = await _mdJson(`/api/study/${req.request_id}?justification=0`);
                const text = study ? _mdReportText(study) : '';
                cached.own = text ? {
                    id: req.request_id, code: req.request_code || '', own: true,
                    date: _mdIso(req.date_time), region: '', text, summary: study.summary || '',
                } : null;
            } catch (_) { cached.own = null; }
            const own = cached.own;
            if (own && !own.summary && _isMeaningfulText(own.text)) {
                _autoSummarizePrev(own, () => _applyPrevLine(el, own));
            }
            _applyPrevLine(el, own);
        });
    }

    function _loadPrevLine(el, cached) {
        const req = el._req;
        cached.prevChecked = true;
        const modality = _mdModalityGroup(req?.modality || '');
        if (!cached.hasPrev || !cached.patientId || !_mdTypedModalities.has(modality)) {
            cached.prev = null;
            return;
        }
        _enqueuePrev(async () => {
            try {
                cached.prev = await _findPreviousExam(req.request_id, req.date_time, modality, cached.patientId);
            } catch (_) { cached.prev = null; }
            const prev = cached.prev;
            if (prev && !prev.summary && _isMeaningfulText(prev.text)) {
                _autoSummarizePrev(prev, () => _applyPrevLine(el, prev));
            }
            _applyPrevLine(el, prev);
        });
    }

    // Generates the missing AI summary of a previous exam in the background,
    // through the shared one-at-a-time warm queue (4 s apart, paused while
    // the tab is hidden or the LLM is failing). Rows whose previous exam has
    // the same report text share one job. `refresh` re-renders the line.
    const _prevSummaryWaiters = new Map(); // report text -> [(summary) => void]
    function _autoSummarizePrev(prev, refresh) {
        prev.pending = true;
        const settle = summary => {
            prev.pending = false;
            if (summary) prev.summary = summary;
            refresh();
        };
        const waiters = _prevSummaryWaiters.get(prev.text);
        if (waiters) { waiters.push(settle); return; }
        _prevSummaryWaiters.set(prev.text, [settle]);
        enqueueAiWarm('imaging', prev.text, null, summary => {
            _prevSummaryWaiters.get(prev.text)?.forEach(fn => fn(summary));
            _prevSummaryWaiters.delete(prev.text);
        });
    }

    // Fourth card line: with a summary, "12 Jun 2026 · abdomen: <summary>"
    // (clamped, tap to expand, click to open the report modal); without one,
    // "Prev CT · 12 Jun 2026 · abdomen" + a Summarize link. Hidden when
    // there is no previous exam.
    function _applyPrevLine(el, prev) {
        const line = el._prevLine;
        if (!line) return;
        line.replaceChildren();
        if (!prev) { line.hidden = true; return; }
        // The heading opens that exam's report modal, like the card's own
        // request code does.
        const openModal = e => {
            e.stopPropagation();
            showRequestModal(prev.id, prev.code, el._patientName, el._req?.modality || '', e.currentTarget, '', '');
        };
        // With an AI summary in hand, there's no need for a separate "Prev
        // CT · date · region" heading — the summary itself (prefixed with
        // date/region for a previous exam) is the whole line, clickable to
        // open that exam's report modal.
        if (prev.summary && !prev.pending) {
            const when = prev.date ? formatDate(prev.date.replace(' ', 'T')) : '';
            const prefix = prev.own ? '' : [when, prev.region].filter(Boolean).join(' · ');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'timeline-prev-head';
            btn.title = 'Open this exam';
            if (prefix) btn.append(`${prefix}: `);
            const em = document.createElement('em');
            em.className = 'timeline-prev-text';
            em.textContent = prev.summary;
            btn.appendChild(em);
            btn.addEventListener('click', openModal);
            line.appendChild(btn);
            line.hidden = false;
            return;
        }
        // Own report, no summary yet: a single "Summarize the report" button
        // instead of a separate "Report" heading + "Summarize" link.
        if (prev.own && !prev.pending) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'timeline-prev-head timeline-prev-action';
            btn.textContent = 'Summarize the report';
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                btn.disabled = true;
                btn.textContent = 'Summarizing…';
                try {
                    prev.summary = await aiSummarize('imaging', prev.text);
                    _applyPrevLine(el, prev);
                } catch (err) {
                    btn.disabled = false;
                    btn.textContent = 'Summarize the report';
                    showToast(`AI summary failed: ${err.message || err}`, 'error');
                }
            });
            line.appendChild(btn);
            line.hidden = false;
            return;
        }
        const head = document.createElement('button');
        head.type = 'button';
        head.className = 'timeline-prev-head';
        head.title = 'Open this exam';
        const when = prev.date ? formatDate(prev.date.replace(' ', 'T')) : '';
        head.textContent = prev.own
            ? 'Report'
            : ['Prev', el.dataset.modality, when, prev.region].filter(Boolean).join(' · ');
        head.addEventListener('click', openModal);
        line.appendChild(head);
        if (prev.pending) {
            line.onclick = null;
            const wait = document.createElement('span');
            wait.className = 'timeline-prev-pending';
            wait.textContent = 'summarizing…';
            line.append(' — ', wait);
        } else {
            line.onclick = null;
            line.append(' — ');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn-link timeline-prev-summarize';
            btn.textContent = 'Summarize';
            btn.addEventListener('click', async e => {
                e.stopPropagation();
                btn.disabled = true;
                btn.textContent = 'Summarizing…';
                try {
                    prev.summary = await aiSummarize('imaging', prev.text);
                    _applyPrevLine(el, prev);
                } catch (err) {
                    btn.disabled = false;
                    btn.textContent = 'Summarize';
                    showToast(`AI summary failed: ${err.message || err}`, 'error');
                }
            });
            line.appendChild(btn);
        }
        line.hidden = false;
    }

    // Lazy PACS study-check lookup (see pacs.py / triggerPacsRefresh above):
    // one GET /api/pacs/<id> per badge as it scrolls into view, same
    // one-shot-per-element shape as scheduleExamObserver. The badge element
    // itself (not its container) is observed and carries the id, since the
    // schedule row and the imaging card use different container attribute
    // names (data-request-id vs data-service-request-id) but both badges
    // get the same data-request-id set directly on them.
    const _pacsStatusCache = {};
    const pacsStatusObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            // The container (avatar/circle), not the badge itself — the
            // badge starts `hidden` (display:none), and a display:none
            // element has no layout box, so it can never register as
            // intersecting the viewport no matter how the page scrolls.
            // Observing the always-visible container avoids that
            // chicken-and-egg deadlock (needing to be visible to trigger
            // the fetch that makes it visible).
            const container = entry.target;
            pacsStatusObserver.unobserve(container);
            const badge = container.querySelector('.pacs-confirmed-badge');
            const id = badge?.dataset.requestId;
            if (!badge || !id) return;
            const apply = (data) => {
                if (data?.outcome === 'performed' || data?.outcome === 'likely') badge.hidden = false;
            };
            if (_pacsStatusCache[id]) { apply(_pacsStatusCache[id]); return; }
            apiFetch(`/api/pacs/${id}`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (!data || !data.enabled) return;
                    _pacsStatusCache[id] = data;
                    apply(data);
                })
                .catch(() => {});
        });
    }, { rootMargin: '200px' });

    function _applyReferrer(el, referrerName) {
        const requesterEl = el._requesterEl;
        if (!requesterEl) return;
        requesterEl.querySelector('span').textContent = referrerName;
        requesterEl.hidden = false;
        if (el._requesterSep) el._requesterSep.hidden = false;
    }

    function _applyPatientAge(el, ageText) {
        const nameBtn = el._nameBtn;
        if (!nameBtn) return;
        nameBtn.textContent = '';
        nameBtn.appendChild(document.createTextNode(el._patientName + ' · '));
        const ageEl = document.createElement('span');
        ageEl.className = 'timeline-card-patient-age';
        ageEl.textContent = ageText;
        nameBtn.appendChild(ageEl);
    }

    // Most-to-least severe → color, matching the FUPU checkbox order
    // (30-Resuscit./31-Critic/32-Urgent/33-Non-urg./34-Consult).
    const _TRIAGE_COLOR_CLASS = {
        'Resuscitation': 'triage-red',
        'Critical':      'triage-yellow',
        'Urgent':        'triage-green',
        'Non-urgent':    'triage-blue',
        'Routine':       'triage-gray',
    };

    // Only the two most severe triage levels are worth surfacing on the
    // schedule row itself — Urgent/Non-urgent/Routine are the common case
    // and would just be noise on every UPU row. Colors are still defined
    // for all 5 above, for whenever the rest need showing too.
    const _TRIAGE_ALERT_LEVELS = new Set(['Resuscitation', 'Critical', 'Urgent']);

    // Appends the ER triage level straight onto the "UPU" section badge
    // (e.g. "UPU: Critical"), colored by severity.
    function _applyTriage(el, triageText) {
        if (!_TRIAGE_ALERT_LEVELS.has(triageText)) return;
        const sectionEl = el._sectionEl;
        if (!sectionEl) return;
        const span = sectionEl.querySelector('span');
        if (!span) return;
        span.textContent = `${el.dataset.section}: ${triageText}`;
        span.classList.add('timeline-triage', _TRIAGE_COLOR_CLASS[triageText] || 'triage-gray');
    }

    function _applyExamLabel(el, { regions, indication }) {
        el.innerHTML = '';
        const modality = el.dataset.modality || '';
        const regionText = regions.length
            ? (modality ? modality + ' · ' : '') + regions.join(', ')
            : modality;
        if (regionText) {
            el.appendChild(document.createTextNode(regionText));
        }
        if (indication) {
            if (regionText) el.append(' · ');
            const em = document.createElement('em');
            em.className = 'timeline-indication';
            em.textContent = indication;
            el.appendChild(em);
        }
    }

    function renderScheduleHero() {
        if (!elements.scheduleHero || !elements.scheduleDayMetrics) return;

        // Update h1 with formatted date range
        const h1 = document.getElementById('schedule-tab-heading');
        if (h1) {
            const start = elements.scheduleStartDate?.value || '';
            const end   = elements.scheduleEndDate?.value   || '';
            const dateToShow = end || start;
            if (dateToShow) {
                h1.textContent = formatDayHeading(dateToShow);
            } else {
                h1.textContent = 'Schedule';
            }
        }

        const total     = scheduleEntries.length;
        const urgent    = scheduleEntries.filter(r => r.priority_code === 'urgent').length;
        const inLab     = scheduleEntries.filter(r => ['draft', 'active'].includes(r.status_code)).length;
        const completed = scheduleEntries.filter(r => ['completed', 'ended'].includes(r.status_code)).length;

        const metricDefs = [
            { label: 'Exams',     value: total,     color: 'var(--primary, #4338ca)' },
            { label: 'Urgent',    value: urgent,    color: 'var(--urgent, #dc2626)' },
            { label: 'In lab',    value: inLab,     color: 'var(--st-inlab, #1d4ed8)' },
            { label: 'Completed', value: completed, color: 'var(--st-completed, #065f46)' },
        ];

        const sub = document.getElementById('scheduleHeroSub');
        if (sub) sub.textContent = `${total} exam${total !== 1 ? 's' : ''} in queue · most recent first`;

        const metricTpl = document.getElementById('schedule-metric-template');
        elements.scheduleDayMetrics.innerHTML = '';
        metricDefs.forEach(m => {
            const div = document.importNode(metricTpl.content, true).firstElementChild;
            const val = div.querySelector('.schedule-metric-value');
            val.textContent = m.value;
            val.style.color = m.color;
            div.querySelector('.schedule-metric-label').textContent = m.label;
            elements.scheduleDayMetrics.appendChild(div);
        });

        // Modality bars
        if (elements.scheduleModBars && total > 0) {
            const modalityCounts = {};
            scheduleEntries.forEach(r => {
                const slug = r.modality || 'other';
                modalityCounts[slug] = (modalityCounts[slug] || 0) + 1;
            });

            const modColors = { radio: 'var(--mod-xr)', ct: 'var(--mod-ct)', irm: 'var(--mod-mr)', eco: 'var(--mod-us)', fluoro: 'var(--mod-fl)', lab: 'var(--mod-lab)' };

            const barTpl = document.getElementById('schedule-mod-bar-template');
            elements.scheduleModBars.innerHTML = '';
            Object.entries(modalityCounts).sort((a, b) => b[1] - a[1]).forEach(([slug, count]) => {
                const bar = document.importNode(barTpl.content, true).firstElementChild;
                const pct = Math.round(count / total * 100);
                const color = modColors[slug] || 'var(--muted)';
                bar.querySelector('.schedule-mod-bar-name').textContent = MODALITY_INFO[slug]?.label || slug;
                const countEl = bar.querySelector('.schedule-mod-bar-count');
                countEl.textContent = count;
                countEl.style.color = color;
                const fill = bar.querySelector('.schedule-mod-bar-fill');
                fill.style.width = `${pct}%`;
                fill.style.background = color;
                elements.scheduleModBars.appendChild(bar);
            });
            elements.scheduleModBars.hidden = false;
        }
    }

    // "2026-06-11" → "Wednesday, 2026-06-11" (string split avoids UTC offset)
    function formatDayHeading(day) {
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
        if (!m) return day;
        const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        if (isNaN(d)) return day;
        const weekday = d.toLocaleDateString('en-US', { weekday: 'long' });
        const dayNum  = d.getDate();
        const month   = d.toLocaleDateString('en-US', { month: 'long' });
        return `${weekday}, ${dayNum} ${month}`;
    }

    // Helper function to extract diagnosis text
    function extractDiagnosisText(encounterData) {
        return encounterData.diagnosis || null;
    }

    // Phone-width QR carousel (the CSS turns .qr-grid into a horizontal
    // scroll-snap strip below 480px): position dots, and mouse drag — touch
    // swipes already scroll it natively.
    function setupQrCarousel() {
        const grid = document.querySelector('.qr-grid');
        const dotsEl = document.getElementById('qrDots');
        if (!grid || !dotsEl) return;
        const carousel = window.matchMedia('(max-width: 480px)');
        const slides = () => [...grid.children].filter(c => c.offsetParent !== null);
        const nearest = () => {
            const g = grid.getBoundingClientRect();
            let best = 0, bestDist = Infinity;
            slides().forEach((c, i) => {
                const r = c.getBoundingClientRect();
                const d = Math.abs(r.left + r.width / 2 - (g.left + g.width / 2));
                if (d < bestDist) { best = i; bestDist = d; }
            });
            return best;
        };
        const updateDots = () => {
            const n = carousel.matches ? slides().length : 0;
            if (dotsEl.children.length !== n) {
                dotsEl.replaceChildren(...Array.from({ length: n }, () => {
                    const dot = document.createElement('span');
                    dot.className = 'qr-dot';
                    return dot;
                }));
            }
            const active = nearest();
            [...dotsEl.children].forEach((dot, i) => dot.classList.toggle('active', i === active));
        };
        grid.addEventListener('scroll', updateDots, { passive: true });
        carousel.addEventListener('change', updateDots);
        // Slides appear/disappear as the patient's QR labels are filled in
        new MutationObserver(updateDots).observe(grid, { subtree: true, childList: true, characterData: true });

        let drag = null;
        grid.addEventListener('pointerdown', e => {
            if (e.pointerType !== 'mouse' || e.button !== 0 || !carousel.matches) return;
            drag = { x: e.clientX, left: grid.scrollLeft };
            grid.setPointerCapture(e.pointerId);
            grid.classList.add('dragging');
        });
        grid.addEventListener('pointermove', e => {
            if (drag) grid.scrollLeft = drag.left - (e.clientX - drag.x);
        });
        const endDrag = () => {
            if (!drag) return;
            drag = null;
            grid.classList.remove('dragging');
            // Snap to the nearest slide (snapping was off while dragging)
            const target = slides()[nearest()];
            if (target) {
                const shift = target.getBoundingClientRect().left - grid.getBoundingClientRect().left;
                grid.scrollTo({ left: grid.scrollLeft + shift, behavior: 'smooth' });
            }
        };
        grid.addEventListener('pointerup', endDrag);
        grid.addEventListener('pointercancel', endDrag);
        updateDots();
    }
    setupQrCarousel();

});
