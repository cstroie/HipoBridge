marked.use({ breaks: true });

const APP_TITLE = 'HippoBridge';
function setPageTitle(prefix) {
    document.title = prefix ? `${prefix} — ${APP_TITLE}` : APP_TITLE;
}

function localDateStr(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

document.addEventListener('DOMContentLoaded', function() {
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
        // AI tab elements
        aiPreExamBtn: document.getElementById('aiPreExamBtn'),
        aiPreExamAnchor: document.getElementById('aiPreExamAnchor'),
        aiEmptyState: document.getElementById('aiEmptyState'),
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
        // Schedule tab elements
        scheduleStartDate: document.getElementById('scheduleStartDate'),
        scheduleEndDate: document.getElementById('scheduleEndDate'),
        refreshScheduleBtn: document.getElementById('refreshScheduleBtn'),
        schedulePatientFilter: document.getElementById('schedulePatientFilter'),
        scheduleLabFilter:     document.getElementById('scheduleLabFilter'),
        scheduleSectionFilter: document.getElementById('scheduleSectionFilter'),
        scheduleLimitSelect:   document.getElementById('scheduleLimitSelect'),
        scheduleTable: document.getElementById('scheduleTable'),
        scheduleBody: document.getElementById('scheduleBody'),
        noSchedule: document.getElementById('noSchedule'),
        scheduleTimeline: document.getElementById('scheduleTimeline'),
        scheduleStatusChips: document.getElementById('scheduleStatusChips'),
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
            showLoginDialog('Session expired or wrong credentials. Please sign in again.');
            throw new Error('Authentication required');
        }
        return resp;
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

        // AI summary buttons (report header, lab trends, pre-exam tab).
        // Per-card buttons (epicrisis, imaging) are wired at render time.
        wireAiButton(elements.aiReportBtn, 'report',
            () => elements.reportCard, () => getPatientClinicalText());
        if (elements.aiLabBtn) elements.aiLabBtn.addEventListener('click', runLabSummary);
        wireAiButton(elements.aiPreExamBtn, 'pre_exam',
            () => elements.aiPreExamAnchor, () => getPatientClinicalText());

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
            elements.refreshScheduleBtn.addEventListener('click', () => fetchScheduleFromInputs(true));
        }
        if (elements.refreshPatientBtn) {
            elements.refreshPatientBtn.addEventListener('click', refreshCurrentPatient);
        }
        if (elements.schedulePatientFilter) {
            elements.schedulePatientFilter.addEventListener('keydown', e => {
                if (e.key === 'Enter') fetchScheduleFromInputs();
            });
        }
        if (elements.scheduleLabFilter) {
            elements.scheduleLabFilter.addEventListener('change', fetchScheduleFromInputs);
        }
        if (elements.scheduleSectionFilter) {
            elements.scheduleSectionFilter.addEventListener('change', () => {
                updateWardPillLabel();
                fetchScheduleFromInputs();
            });
        }
        if (elements.scheduleLimitSelect) {
            elements.scheduleLimitSelect.addEventListener('change', fetchScheduleFromInputs);
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

        // Schedule status chips
        elements.scheduleStatusChips?.addEventListener('click', e => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            elements.scheduleStatusChips.querySelectorAll('.chip').forEach(c => c.classList.remove('chip-active'));
            chip.classList.add('chip-active');
            activeScheduleStatusFilter = chip.dataset.status;
            renderSchedule();
        });
    }
    
    function switchTab(tabId) {
        // Update active nav item and aria-current
        elements.navItems.forEach(nav => {
            nav.classList.remove('active');
            nav.removeAttribute('aria-current');
        });
        // Prefer .nav-btn over the patient-ctx-pill when both share data-tab
        const activeNavItem = document.querySelector(`.nav-btn.nav-item[data-tab="${tabId}"]`)
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

    async function fetchServiceBundle() {
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
            const result = await fetchServiceBundle(); // memoized; also warms Laboratory
            if (gen !== dataGeneration) return;
            if (pendingReportData) {
                pendingReportData.analysesData = result.data || { resourceType: 'Bundle', entry: [] };
            }
        } catch (err) {
            log('Prefetch imaging failed (silent):', err);
        }
    }

    async function prefetchLaboratory(patientData, gen) {
        if (gen !== dataGeneration) return;
        try {
            await fetchServiceBundle(); // shares cachedServiceRequests with imaging
            if (gen !== dataGeneration) return;
            const sd = new Date(); sd.setDate(sd.getDate() - 90);
            await apiFetch(`/fhir/Observation?patient=${encodeURIComponent(patientData.id)}&start_date=${localDateStr(sd)}`);
        } catch (err) {
            log('Prefetch laboratory failed (silent):', err);
        }
    }

    async function prefetchEpicrisis(patientData, gen) {
        if (gen !== dataGeneration) return;
        try {
            const checkoutIds = extractCheckoutIds(patientData);
            if (!checkoutIds.length) return;
            await limitedMap(checkoutIds, MAX_CONCURRENT_REQUESTS, async id => {
                if (gen !== dataGeneration) return null;
                try { return await fetchEncounterDataForCheckout(id); }
                catch { return null; }
            });
        } catch (err) {
            log('Prefetch epicrisis failed (silent):', err);
        }
    }

    async function loadImagingLazily() {
        if (!pendingAnalysesData || elements.imagingGrid?.dataset.loaded) return;
        elements.imagingGrid.dataset.loaded = '1';
        const { patientData } = pendingAnalysesData;
        const patientLabel = formatPatientName(patientData.name);
        showLoading(`Loading imaging studies for ${patientLabel}…`);
        try {
            setLoadingStep('Querying Hipocrate for imaging requests…');
            const result = await fetchServiceBundle();
            const bundle = result.data || { resourceType: 'Bundle', entry: [] };
            const IMAGING = ['radio', 'ct', 'irm', 'eco', 'rads'];
            const entries = (bundle.entry || []).filter(e => IMAGING.includes(e.resource?.code?.coding?.[0]?.code));
            setLoadingStep(entries.length ? `Organising ${entries.length} imaging studies…` : 'No imaging studies found.');
            await populateStudyGrid(entries, {
                grid: elements.imagingGrid, noData: elements.imagingNoData,
                eyebrow: elements.imagingEyebrow, eyebrowLabel: `Imaging · ${patientLabel}`,
                metaId: 'imagingMeta', types: IMAGING,
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
        const patientLabel = formatPatientName(patientData.name);
        showLoading(`Loading lab results for ${patientLabel}…`);
        try {
            setLoadingStep('Querying Hipocrate for lab requests…');
            const result = await fetchServiceBundle();
            const bundle = result.data || { resourceType: 'Bundle', entry: [] };
            const LAB = ['lab'];
            const entries = (bundle.entry || []).filter(e => LAB.includes(e.resource?.code?.coding?.[0]?.code));
            setLoadingStep(entries.length ? `Organising ${entries.length} lab results…` : 'No lab results found.');
            await populateStudyGrid(entries, {
                grid: elements.labGrid, noData: elements.labNoData,
                eyebrow: elements.labEyebrow, eyebrowLabel: `Laboratory · ${patientLabel}`,
                metaId: 'labMeta', types: LAB,
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
        const name = pendingReportData.patientData?.name?.[0]?.text || 'patient';
        showLoading(`Assembling clinical report for ${name}…`);
        try {
            setLoadingStep('Compiling diagnoses, admissions and imaging history…');
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
        const name = pendingEpicrisisData?.name?.[0]?.text || 'patient';
        showLoading(`Loading hospitalization records for ${name}…`);
        try {
            setLoadingStep('Fetching hospitalisation episodes from Hipocrate…');
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
                    showLoading(`Loading record for ${chosen.name?.[0]?.text || chosen.id}…`);
                    setLoadingStep('Fetching full patient record from Hipocrate…');
                    const r = await apiFetch(`/fhir/Patient/${chosen.id}`);
                    searchResult.patientData = r.ok ? await r.json() : chosen;
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

            const patientName = patientData.name?.[0]?.text || patientCode;
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
            pendingReportData = { patientData, analysesData: { resourceType: 'Bundle', entry: [] } };
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
            const r = await apiFetch(`/fhir/Patient/${patientCode}?refresh=1`);
            if (!r.ok) throw new Error(`Server error: ${r.status}`);
            const patientData = await r.json();

            displayPatientData(patientData);

            pendingAnalysesData = { patientCode, patientData };
            cachedServiceRequests = null;
            if (elements.imagingGrid) delete elements.imagingGrid.dataset.loaded;
            if (elements.labGrid) delete elements.labGrid.dataset.loaded;

            pendingEpicrisisData = patientData;
            if (elements.epicrisisContent) delete elements.epicrisisContent.dataset.loaded;

            pendingReportData = { patientData, analysesData: { resourceType: 'Bundle', entry: [] } };
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
            const searchResponse = await apiFetch(`/fhir/Patient?q=${encodeURIComponent(identifier)}`);
            
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
            
            if (searchData.resourceType === "Patient") {
                patientCode = searchData.id;
                patientData = searchData;
            } else if (searchData.resourceType === "Bundle" && searchData.entry && searchData.entry.length > 0) {
                if (searchData.entry.length === 1) {
                    patientCode = searchData.entry[0].resource.id;
                    const r = await apiFetch(`/fhir/Patient/${patientCode}`);
                    patientData = r.ok ? await r.json() : searchData.entry[0].resource;
                } else {
                    // Multiple matches — let the user choose
                    return {
                        success: false,
                        needsSelection: true,
                        candidates: searchData.entry.map(e => e.resource)
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
                const nameObj = Array.isArray(patient.name) ? patient.name[0] : patient.name;
                const name = nameObj?.text || [nameObj?.family, ...(nameObj?.given || [])].filter(Boolean).join(' ') || patient.id;
                const cnp = extractCNP(patient.identifier);
                const dob = formatBirthDate(patient.birthDate);
                const gender = patient.gender ? (patient.gender === 'male' ? 'M' : 'F') : null;
                const meta = [cnp, dob, gender].filter(Boolean).join(' · ');
                const btn = document.createElement('button');
                btn.className = 'btn-secondary';
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
            
            const analysesResponse = await apiFetch(`/fhir/ServiceRequest?patient=${patientCode}`);
            
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
                        data: { resourceType: "Bundle", entry: [] },
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
        if (elements.patientReportBlocks) delete elements.patientReportBlocks.dataset.blocks;
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

    async function fetchWhoami() {
        if (whoamiData) return whoamiData;
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
        return whoamiData;
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

        modal.querySelector('.user-logout-btn').addEventListener('click', async () => {
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
            const displayName = user.display_name
                ? user.display_name.toLowerCase()
                : (user.username || '').replace(/\./g, ' ');
            nameEl.textContent = displayName || 'Unknown user';
            modal.querySelector('.user-detail-username').textContent = user.username || '—';
            modal.querySelector('.user-detail-id').textContent = user.id || '—';
            modal.querySelector('.user-detail-reports').textContent = canWriteReports ? 'Can write reports' : '—';
        } catch (err) {
            nameEl.textContent = 'Unavailable';
            showToast(`Could not load user info: ${err.message}`, 'error');
        }
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
        if (noDataEl) noDataEl.style.display = visible === 0 ? 'block' : 'none';
    }

    function filterLabGrid(section = 'all') {
        if (!elements.labGrid) return;
        let visible = 0;
        elements.labGrid.querySelectorAll('.analysis-card').forEach(card => {
            const secs = card.dataset.labSection ? card.dataset.labSection.split('\t') : [];
            const show = section === 'all' || secs.includes(section);
            card.style.display = show ? 'block' : 'none';
            if (show) visible++;
        });
        if (elements.labNoData) elements.labNoData.style.display = visible === 0 ? 'block' : 'none';
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
            container.appendChild(chip);
        }
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

    function resetAiTab() {
        if (elements.aiEmptyState) elements.aiEmptyState.hidden = false;
        if (elements.aiReportBtn) elements.aiReportBtn.hidden = true;
        if (elements.aiPreExamBtn) elements.aiPreExamBtn.hidden = true;
        if (elements.aiLabBtn) elements.aiLabBtn.hidden = true;
        // Drop any rendered AI cards from a previous patient. querySelectorAll
        // does not descend into <template> content, so the template card is safe.
        document.querySelectorAll('.ai-summary-card').forEach(card => card.remove());
        for (const btn of [elements.aiReportBtn, elements.aiPreExamBtn, elements.aiLabBtn]) {
            if (btn) btn._aiCard = null;
        }
        labAiText = '';
        labHasAbnormal = false;
    }

    // Clinical-only text used by the Report and Pre-Exam summaries —
    // deliberately excludes patient demographics (name/DOB/CNP), which the
    // model tends to fabricate or garble when asked to restate them; the
    // card is paired with the already-rendered, deterministic patient
    // identity on the Report tab instead. Falls back to the full markdown
    // if the clinical-only stash isn't populated (e.g. an older cached load).
    function getPatientClinicalText() {
        const clinical = elements.patientReportBlocks?.dataset.clinicalMarkdown;
        if (clinical && clinical.trim()) return clinical;
        return elements.patientReportMarkdown?.dataset.markdown || null;
    }

    // Toggle the availability of the singleton AI buttons when patient
    // clinical text becomes (un)available.
    function updateAiEmptyState() {
        const hasContent = !!getPatientClinicalText();
        if (elements.aiEmptyState) elements.aiEmptyState.hidden = hasContent;
        if (elements.aiReportBtn) elements.aiReportBtn.hidden = !hasContent;
        if (elements.aiPreExamBtn) elements.aiPreExamBtn.hidden = !hasContent;
        if (hasContent) {
            // Silently redisplay a previously generated summary for this patient, if any.
            runAiSummary(elements.aiReportBtn, 'report',
                () => elements.reportCard, getPatientClinicalText, { auto: true });
            runAiSummary(elements.aiPreExamBtn, 'pre_exam',
                () => elements.aiPreExamAnchor, getPatientClinicalText, { auto: true });
        }
    }

    // opts.force bypasses the server cache and regenerates. opts.checkOnly
    // skips generation entirely — returns null if nothing is cached yet,
    // instead of calling the LLM. Server caches by (kind, sha256(text)), so
    // the same text always redisplays the same summary until forced.
    async function aiSummarize(kind, text, opts = {}) {
        const resp = await apiFetch('/api/ai/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind, text, force: !!opts.force, check_only: !!opts.checkOnly }),
        });
        let data = {};
        try { data = await resp.json(); } catch (_) { /* non-JSON error */ }
        if (!resp.ok || data.status === 'error') {
            throw new Error(data.message || `AI summary failed (HTTP ${resp.status})`);
        }
        if (data.status === 'not_cached') return null;
        return data.summary || '';
    }

    // Kinds served by /api/ai/summarize/stream (report/epicrisis/pre_exam —
    // the ones long enough that perceived latency matters; imaging/lab stay
    // on the plain aiSummarize() endpoint above).
    const STREAMING_KINDS = new Set(['report', 'epicrisis', 'pre_exam']);

    // Rare sentinel (ASCII Unit Separator) the server uses to signal a
    // mid-stream failure it can no longer report via HTTP status, since the
    // response has already committed to 200 once streaming starts. Must
    // match hipobridge.py's _STREAM_ERROR_SENTINEL exactly.
    const STREAM_ERROR_SENTINEL = '\x1f';

    // Streaming counterpart to aiSummarize(): POSTs to /api/ai/summarize/stream
    // and calls onChunk(piece) as text arrives. Always force:true (mirrors
    // runAiSummary's manual-click path, the only caller) — the silent
    // cache-probe path never streams. Throws on error, same contract as
    // aiSummarize(), so callers need no special-casing.
    async function aiSummarizeStream(kind, text, onChunk) {
        const resp = await apiFetch('/api/ai/summarize/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind, text, force: true }),
        });
        if (!resp.ok) {
            let data = {};
            try { data = await resp.json(); } catch (_) { /* non-JSON error */ }
            throw new Error(data.message || `AI summary failed (HTTP ${resp.status})`);
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            if (buffer.includes(STREAM_ERROR_SENTINEL)) {
                const [, , message] = buffer.split(STREAM_ERROR_SENTINEL);
                throw new Error(message || 'AI summary failed');
            }
            if (buffer) { onChunk(buffer); buffer = ''; }
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
    const AI_WARM_GAP_MS = 4000;

    function enqueueAiWarm(kind, text, gen) {
        if (!text) return;
        aiWarmQueue.push({ kind, text, gen });
        if (!aiWarmRunning) processAiWarmQueue();
    }

    async function processAiWarmQueue() {
        aiWarmRunning = true;
        while (aiWarmQueue.length) {
            const job = aiWarmQueue.shift();
            if (job.gen === dataGeneration) {
                try {
                    await aiSummarize(job.kind, job.text);
                } catch (err) {
                    // Likely misconfigured/unreachable — stop trying for this session
                    // rather than burning through the rest of the queue on failures.
                    log('Background AI warm failed, pausing warm queue (silent):', err);
                    aiWarmQueue = [];
                    break;
                }
            }
            if (aiWarmQueue.length) await new Promise(r => setTimeout(r, AI_WARM_GAP_MS));
        }
        aiWarmRunning = false;
    }

    function makeAiCard(inline) {
        const card = document.getElementById('ai-card-template').content
            .firstElementChild.cloneNode(true);
        if (inline) card.classList.add('ai-card--inline');
        return card;
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
            button._aiCard = card;
        }

        if (opts.auto) {
            try {
                const cached = await aiSummarize(kind, text, { checkOnly: true });
                if (cached === null) return; // nothing cached yet — leave the button untouched
                placeAiCard(card, getAnchor(), opts.intoAnchorParent?.());
                const body = card.querySelector('.ai-summary-body');
                card.classList.remove('ai-card-error');
                body.classList.remove('ai-summary-loading');
                body.innerHTML = marked.parse(cached || '_(empty response)_');
            } catch (_) {
                // Silent — an auto-probe failure shouldn't surface to the user.
            }
            return;
        }

        placeAiCard(card, getAnchor(), opts.intoAnchorParent?.());

        const body = card.querySelector('.ai-summary-body');
        card.classList.remove('ai-card-error');
        body.classList.add('ai-summary-loading');
        body.textContent = 'Generating…';
        button.disabled = true;
        try {
            if (STREAMING_KINDS.has(kind)) {
                let full = '';
                let first = true;
                await aiSummarizeStream(kind, text, (piece) => {
                    if (first) {
                        // First chunk arrived — drop the "Generating…"
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
                body.innerHTML = marked.parse(full || '_(empty response)_');
            } else {
                const summary = await aiSummarize(kind, text, { force: true });
                body.classList.remove('ai-summary-loading');
                body.innerHTML = marked.parse(summary || '_(empty response)_');
            }
        } catch (err) {
            console.error(`AI summary failed (${kind}):`, err);
            body.classList.remove('ai-summary-loading', 'ai-summary-streaming');
            card.classList.add('ai-card-error');
            body.textContent = `AI summary failed: ${err.message}`;
        } finally {
            button.disabled = false;
        }
    }

    function wireAiButton(button, kind, getAnchor, getText, opts = {}) {
        if (!button) return;
        button.addEventListener('click', () => runAiSummary(button, kind, getAnchor, getText, opts));
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
            button._aiCard = card;
        }
        placeAiCard(card, elements.trendsContainer?.firstChild || null, elements.trendsContainer);
        card.classList.remove('ai-card-error');
        const badge = card.querySelector('.ai-summary-badge');
        if (badge) badge.hidden = true;
        const body = card.querySelector('.ai-summary-body');
        body.classList.remove('ai-summary-loading');
        body.innerHTML = marked.parse('**All lab values are within their reference intervals.**');
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
        
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            analysesData.entry.forEach(entry => {
                const serviceRequest = entry.resource;
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                const analysisText = serviceRequest.code?.coding?.[0]?.display || 'analysis';
                // Skip unknown types
                if (!modalityMap[analysisType]) return;

                if (!analysesByModality[analysisType]) {
                    analysesByModality[analysisType] = [];
                }

                analysesByModality[analysisType].push({
                    serviceRequest,
                    analysisType,
                    analysisText,
                    examDateString: serviceRequest.authoredOn || null
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
                ? `/fhir/ImagingStudy/${serviceRequestId}`
                : `/fhir/DiagnosticReport/${serviceRequestId}`;
            const reportResponse = await apiFetch(endpoint);

            if (!reportResponse.ok) {
                log(`Report not found for service request ${serviceRequestId}`);
                return null;
            }

            const reportData = await reportResponse.json();
            let content = null;
            if (reportData.note && reportData.note.length > 0) {
                content = reportData.note.map(n => n.text).filter(Boolean).join('\n\n').trim();
            } else if (reportData.conclusion) {
                content = reportData.conclusion;
            } else if (reportData.presentedForm && reportData.presentedForm.length > 0) {
                const forms = reportData.presentedForm;
                const multiStudy = forms.length > 1;
                content = forms
                    .filter(f => f.data)
                    .map(f => multiStudy && f.title ? `##### ${f.title}\n\n${f.data}` : f.data)
                    .join('\n\n---\n\n')
                    .trim();
            } else if (reportData.result && reportData.result.length > 0) {
                content = reportData.result
                    .filter(r => r.display)
                    .map(r => r.display)
                    .join('\n\n')
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
            const resp = await apiFetch(`/fhir/ImagingStudy/${serviceRequestId}`);
            if (!resp.ok) return { indication: '', body: '' };
            const data = await resp.json();
            const notes = data.note || [];
            const isIndication = n => n.category?.[0]?.text === 'clinical-indication';
            const join = arr => arr.map(n => n.text).filter(Boolean).join('\n\n').trim();
            const indication = join(notes.filter(isIndication));
            // Report body: non-indication notes, then the same fallback chain
            // getReportContent uses, so studies that carry findings via
            // conclusion/presentedForm/result don't silently vanish.
            let body = join(notes.filter(n => !isIndication(n)));
            if (!body && data.conclusion) {
                body = data.conclusion;
            } else if (!body && data.presentedForm?.length) {
                const forms = data.presentedForm;
                const multi = forms.length > 1;
                body = forms
                    .filter(f => f.data)
                    .map(f => multi && f.title ? `##### ${f.title}\n\n${f.data}` : f.data)
                    .join('\n\n---\n\n')
                    .trim();
            } else if (!body && data.result?.length) {
                body = data.result.filter(r => r.display).map(r => r.display).join('\n\n').trim();
            }
            // Signing/reporting physician — same fields the analyses-tab card
            // uses (resultsInterpreter, falling back to performer.actor).
            // Only meaningful once a report actually exists: without one,
            // performer falls back server-side to the requesting physician,
            // which would misattribute the (nonexistent) report.
            const physician = body
                ? (data.resultsInterpreter?.[0]?.display || data.performer?.[0]?.actor?.display || '')
                : '';
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
                admissionDate: encounterData.period?.start || null,
                dischargeDate: encounterData.period?.end   || null,
                attender: (() => {
                    const p = encounterData.participant?.find(p =>
                        p.type?.some(t => t.coding?.some(c => c.code === 'ATND'))
                    );
                    return p?.individual?.display || null;
                })(),
                service: encounterData.serviceType?.display || null,
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
       
    async function displayPatientReport(patientData, analysesData) {
        log('Displaying patient report data');

        const reportCard = elements.reportCard;
        const markdownStore = elements.patientReportMarkdown;
        if (reportCard) reportCard.hidden = true;

        try {
            // ── §1 Patient identity ──────────────────────────────────────
            const name     = formatPatientName(patientData.name);
            const age      = calculateAge(patientData.birthDate);
            const gender   = formatGender(patientData.gender);
            const dob      = formatBirthDate(patientData.birthDate);
            const cnp      = extractCNP(patientData.identifier) || '';
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

            const patHipoUrl = (patientData.extension || []).find(e => e.url === 'hipocrateUrl')?.valueUri;
            const pidWrap = document.getElementById('reportPatientIdWrap');
            if (pidWrap) {
                pidWrap.innerHTML = '';
                if (pid && patHipoUrl) {
                    const a = document.createElement('a');
                    a.href = patHipoUrl;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.textContent = pid;
                    pidWrap.appendChild(a);
                } else {
                    pidWrap.textContent = pid;
                }
            }

            const ext = patientData.extension || [];
            const weight = (ext.find(e => e.url?.endsWith('body-weight')) || {}).valueString || '';
            const height = (ext.find(e => e.url?.endsWith('height'))      || {}).valueString || '';
            const weightWrap = document.getElementById('reportWeightWrap');
            const heightWrap = document.getElementById('reportHeightWrap');
            if (weight && weightWrap) { document.getElementById('reportWeight').textContent = weight + ' kg'; weightWrap.hidden = false; }
            else if (weightWrap) weightWrap.hidden = true;
            if (height && heightWrap) { document.getElementById('reportHeight').textContent = height + ' cm'; heightWrap.hidden = false; }
            else if (heightWrap) heightWrap.hidden = true;

            // ── §2 + §4 Encounters (parallel with analyses) ──────────────
            const [analysesMarkdown, epicrisisMarkdown, encounters] = await Promise.all([
                analysesData ? populateAnalysesMarkdown(analysesData) : Promise.resolve(''),
                generateEpicrisisMarkdown(patientData),
                (async () => {
                    const checkoutIds = new Set(extractCheckoutIds(patientData));
                    const checkinIds  = extractCheckinIds(patientData);
                    const allIds = [...checkinIds, ...checkoutIds]; // active admissions first
                    if (!allIds.length) return [];
                    const enc = await limitedMap(allIds, MAX_CONCURRENT_REQUESTS,
                        async id => {
                            try {
                                const type = checkoutIds.has(id) ? 'checkout' : 'checkin';
                                if (cache.encounters[id]) return cache.encounters[id];
                                const r = await apiFetch(`/fhir/Encounter/${id}?type=${type}`);
                                if (!r.ok) return null;
                                const data = await r.json();
                                cachePut(cache.encounters, id, data);
                                return data;
                            } catch { return null; }
                        });
                    return enc
                        .map((e, i) => e && e.resourceType === 'Encounter' ? { enc: e, id: allIds[i] } : null)
                        .filter(Boolean)
                        .sort((a, b) => {
                            const da = a.enc.period?.end || a.enc.period?.start || '';
                            const db = b.enc.period?.end || b.enc.period?.start || '';
                            return db > da ? 1 : -1;
                        });
                })()
            ]);

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
                (enc.note || []).forEach(n => {
                    if (!n.text) return;
                    const clean = n.text
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
                const start = enc.period?.start ? formatDate(enc.period.start) : '';
                const end   = enc.period?.end   ? formatDate(enc.period.end)   : '';
                const ms    = (enc.period?.start && enc.period?.end)
                    ? new Date(enc.period.end) - new Date(enc.period.start) : 0;
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

            // A checkin encounter's "in-progress" status is a static artifact
            // of the checkin.asp scrape — it never updates once the patient
            // is discharged, so a checkin can still claim "in-progress" long
            // after a checkout for that same stay exists (confirmed live: a
            // patient checked in 2026-07-15 and discharged 2026-07-21 still
            // showed "Current Admission: ...present (ongoing)" right next to
            // its own separate, complete "Last Admission" section for the
            // exact same dates). Treat a checkin as genuinely active only if
            // it starts after every already-known checkout has concluded —
            // i.e. it's a fresh admission, not one a checkout already closed.
            const latestCheckoutEnd = encounters
                .filter(e => e.enc.status !== 'in-progress')
                .reduce((latest, e) => {
                    const end = e.enc.period?.end || e.enc.period?.start || '';
                    return end > latest ? end : latest;
                }, '');
            const activeAdm = encounters.find(e =>
                e.enc.status === 'in-progress' &&
                (!latestCheckoutEnd || (e.enc.period?.start || '') > latestCheckoutEnd));
            const lastDischarge = encounters.find(e => e.enc.status !== 'in-progress' && isSubstantiveText(extractEpicrisisText(e.enc)));

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

            // §3 Recent imaging — up to 5 most recent entries from analysesData
            const secImaging = document.getElementById('reportSectionImaging');
            const imagingList = document.getElementById('reportImagingList');
            if (secImaging) secImaging.hidden = true;
            const MOD_SHORT = { radio: 'XR', ct: 'CT', irm: 'MR', eco: 'US', rads: 'FL' };
            const MOD_VAR   = { radio: '--mod-xr', ct: '--mod-ct', irm: '--mod-mr', eco: '--mod-us', rads: '--mod-fl' };
            // Hoisted so the markdown builder below can reference them
            let entries = [], reports = [], indications = [];
            if (imagingList && analysesData?.entry?.length) {
                const candidates = [...analysesData.entry]
                    .filter(e => MOD_SHORT[e.resource?.code?.coding?.[0]?.code])
                    .sort((a, b) => (b.resource.authoredOn || '') > (a.resource.authoredOn || '') ? 1 : -1)
                    .slice(0, 20); // fetch more than needed so we can skip empty ones

                const candidateReports = await limitedMap(candidates, MAX_CONCURRENT_REQUESTS, e => {
                    const sr = e.resource;
                    return getImagingReportParts(sr.id);
                });

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
                entries.forEach((entry, idx) => {
                    const sr = entry.resource;
                    const mod  = sr.code?.coding?.[0]?.code || '';
                    const desc = sr.code?.coding?.[0]?.display || MODALITY_INFO[mod]?.label || mod;
                    const date = sr.authoredOn ? formatDate(sr.authoredOn) : '';
                    const code = sr.identifier?.[0]?.value || sr.id || '';
                    const isUrgent = sr.priority === 'urgent';
                    const physician = physicians[idx] || '';
                    const reportText = reports[idx] || '';
                    const indication = indications[idx] || '';
                    const regions = (sr.bodySite || []).map(b => b.text).filter(Boolean).join(', ');

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
            // pre_exam clinical text, which previously never saw any lab
            // data at all (pre_exam's own prompt already claims to use
            // "labs" — this fulfils that). Scoped to the current/last
            // hospitalization period (not a fixed lookback window) — only
            // modified (out-of-range) analytes, last value per analyte,
            // grouped by date. Reference range is omitted here on purpose:
            // the H/L flag + colour already say "abnormal"; the exact normal
            // range is one tap away in the dedicated Lab tab.
            function isAbnormalObservation(obs) {
                const flag = obs.interpretation?.[0]?.text;
                if (flag === 'H' || flag === 'L') return true;
                const v = obs.valueQuantity?.value;
                if (v == null) return false;
                const low = obs.referenceRange?.[0]?.low?.value;
                const high = obs.referenceRange?.[0]?.high?.value;
                return (low != null && v < low) || (high != null && v > high);
            }

            // One row per modified (out-of-range) analyte, last value only,
            // grouped by date so a same-day panel doesn't repeat its date.
            function collectLabItems(observations) {
                const latestNumeric = new Map();
                for (const obs of observations) {
                    const name = obs.code?.text;
                    const date = obs.effectiveDateTime || '';
                    if (!name || !date || obs.valueQuantity?.value == null) continue;
                    const prev = latestNumeric.get(name);
                    if (!prev || date > prev.date) latestNumeric.set(name, { obs, date });
                }
                const items = [];
                for (const { obs, date } of latestNumeric.values()) {
                    if (!isAbnormalObservation(obs)) continue;
                    const v = obs.valueQuantity.value;
                    const unit = obs.valueQuantity.unit || '';
                    const flag = obs.interpretation?.[0]?.text
                        || (obs.referenceRange?.[0]?.low?.value != null && v < obs.referenceRange[0].low.value ? 'L'
                            : obs.referenceRange?.[0]?.high?.value != null && v > obs.referenceRange[0].high.value ? 'H' : '');
                    items.push({ name: obs.code.text, date, value: `${v}${unit ? ' ' + unit : ''}`, flag });
                }
                items.sort((a, b) => b.date.localeCompare(a.date));
                return items;
            }

            function labItemsToMarkdown(items) {
                if (!items.length) return '';
                let md = '## Recent Labs\n\n';
                let lastDate = null;
                for (const item of items) {
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
                let lastDate = null;
                let tbody = null;
                for (const item of items) {
                    if (item.date !== lastDate) {
                        const heading = document.createElement('p');
                        heading.className = 'lab-section-heading';
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
                // Scope to the current/last hospitalization period rather than a
                // fixed lookback window — an ongoing admission has no end yet.
                const periodStart = (activeAdm || lastDischarge)?.enc.period?.start;
                const periodEnd = activeAdm ? undefined : lastDischarge?.enc.period?.end;
                if (periodStart) {
                    const params = new URLSearchParams({ patient: pid, start_date: localDateStr(new Date(periodStart)) });
                    if (periodEnd) params.set('end_date', localDateStr(new Date(periodEnd)));
                    const labResp = await apiFetch(`/fhir/Observation?${params}`);
                    if (labResp.ok) {
                        const labBundle = await labResp.json();
                        labItems = collectLabItems((labBundle.entry || []).map(e => e.resource).filter(Boolean));
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
                    const start = enc.period?.start ? formatDate(enc.period.start) : '';
                    const end   = enc.period?.end   ? formatDate(enc.period.end)   : '';
                    if (!start && !end) return; // skip entries with no date
                    const rawDx = extractDiagnosisText(enc) || '';
                    const dx    = rawDx === '-' ? '' : rawDx;
                    const service = enc.serviceType?.display || enc.location?.slice(-1)[0]?.location?.display || '';
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
                const start = enc.period?.start ? formatDate(enc.period.start) : '';
                const end   = enc.period?.end   ? formatDate(enc.period.end)   : '';
                const ms    = (enc.period?.start && enc.period?.end)
                    ? new Date(enc.period.end) - new Date(enc.period.start) : 0;
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

            let admissionsMd = '';
            if (activeAdm) {
                admissionsMd += admissionMarkdown('Current Admission', activeAdm.enc, true);
                const sparse = buildCheckinText(activeAdm.enc).length < SPARSE_THRESHOLD;
                if (sparse && lastDischarge)
                    admissionsMd += admissionMarkdown('Last Admission', lastDischarge.enc, false);
            } else if (lastDischarge) {
                admissionsMd += admissionMarkdown('Last Admission', lastDischarge.enc, false);
            }

            let imagingMd = '';
            if (reports.some(Boolean)) {
                imagingMd = '## Recent Imaging\n\n';
                entries.forEach((entry, idx) => {
                    if (!reports[idx]) return; // indication-only, no report to summarise
                    const sr   = entry.resource;
                    const mod  = sr.code?.coding?.[0]?.code || '';
                    const desc = sr.code?.coding?.[0]?.display || MODALITY_INFO[mod]?.label || mod;
                    const date = sr.authoredOn ? formatDate(sr.authoredOn) : '';
                    const code = sr.identifier?.[0]?.value || sr.id || '';
                    imagingMd += `### ${desc}  ·  ${date}${code ? '  #' + code : ''}\n\n${reports[idx]}\n\n`;
                });
            }

            // ── Hospitalisation timeline (mirrors the #reportTimeline rows above) ──
            function buildTimelineMarkdown(encs) {
                const lines = [];
                encs.forEach(item => {
                    const enc   = item.enc;
                    const start = enc.period?.start ? formatDate(enc.period.start) : '';
                    const end   = enc.period?.end   ? formatDate(enc.period.end)   : '';
                    if (!start && !end) return;
                    const rawDx = extractDiagnosisText(enc) || '';
                    const dx    = rawDx === '-' ? '' : rawDx;
                    const service = enc.serviceType?.display || enc.location?.slice(-1)[0]?.location?.display || '';
                    const range = end ? `${start}→${end}` : start;
                    const label = [service, dx].filter(Boolean).join(' — ');
                    lines.push(`- **${range}**${label ? ' — ' + label : ''}`);
                });
                if (!lines.length) return '';
                return '## Hospitalisation Timeline\n\n' + lines.join('\n') + '\n\n';
            }
            const timelineMd = buildTimelineMarkdown(encounters);

            const combined = patientMarkdown + admissionsMd + labsMd + imagingMd + timelineMd;
            if (markdownStore) markdownStore.dataset.markdown = combined;

            // Structured payload for the AI tab: imaging reports are already
            // known-typed here (reports[idx], fetched per-study from their own
            // API endpoint) — send them as-is, no re-guessing. The admission
            // narrative(s) are HippoBridge's one remaining free-text blob with
            // no further structure, sent separately for server-side segmentation.
            // clinicalMarkdown deliberately excludes patientMarkdown (name/DOB/
            // CNP) — the Quick Summary feature reads real patient identity from
            // already-rendered DOM fields instead of asking the model to guess
            // it from raw text (confirmed live: an ungrounded small model will
            // confidently fabricate age/sex rather than omit them).
            if (elements.patientReportBlocks) {
                const typedBlocks = entries
                    .map((entry, idx) => ({ hint_type: 'imaging', text: reports[idx] }))
                    .filter(b => b.text);
                elements.patientReportBlocks.dataset.blocks = JSON.stringify({
                    typed_blocks: typedBlocks,
                    narrative: narrativeParts.join('\n\n'),
                });
                elements.patientReportBlocks.dataset.clinicalMarkdown = admissionsMd + labsMd + imagingMd;
            }

            if (reportCard) reportCard.hidden = false;
            log('Patient report displayed successfully');

        } catch (error) {
            console.error('Error displaying patient report:', error);
        }
    }
    
    async function generatePatientMarkdown(patientData, primaryDiagnosis) {
        log('Generating patient report markdown');

        const name = formatPatientName(patientData.name);
        const age = calculateAge(patientData.birthDate);
        const gender = formatGender(patientData.gender);
        const dob = formatBirthDate(patientData.birthDate);
        const cnp = extractCNP(patientData.identifier) || 'N/A';

        let markdown = `# PATIENT CLINICAL REPORT\n\n`;
        markdown += `## Patient\n\n`;
        markdown += `**Name:** ${name}  \n`;
        markdown += `**Age:** ${age}  \n`;
        markdown += `**Sex:** ${gender}  \n`;
        markdown += `**DOB:** ${dob}  \n`;
        markdown += `**CNP:** ${cnp}  \n`;
        if (primaryDiagnosis) markdown += `**Primary Diagnosis:** ${primaryDiagnosis}  \n`;
        markdown += `\n`;

        log('Patient report markdown generated successfully');
        return markdown;
    }
    
    // Helper function to fetch encounter data for a checkout ID
    async function fetchEncounterDataForCheckout(checkoutId) {
        // check cache first
        if (cache.encounters[checkoutId]) {
            return cache.encounters[checkoutId];
        }

        try {
            const response = await apiFetch(`/fhir/Encounter/${checkoutId}?type=checkout`);

            if (!response.ok) {
                console.error(`Error fetching encounter data for checkout ${checkoutId}:`, response.status);
                return null;
            }
            
            const encounterData = await response.json();
            cachePut(cache.encounters, checkoutId, encounterData);
            log(`Encounter data fetched successfully for checkout ${checkoutId}:`, encounterData);
            return encounterData;
            
        } catch (error) {
            console.error(`Error fetching encounter data for checkout ${checkoutId}:`, error);
            return null;
        }
    }

    // Helper function to fetch encounter data for a checkin ID (active admission, not yet discharged)
    async function fetchEncounterDataForCheckin(checkinId) {
        if (cache.encounters[checkinId]) {
            return cache.encounters[checkinId];
        }
        try {
            const response = await apiFetch(`/fhir/Encounter/${checkinId}?type=checkin`);
            if (!response.ok) {
                console.error(`Error fetching encounter data for checkin ${checkinId}:`, response.status);
                return null;
            }
            const encounterData = await response.json();
            cachePut(cache.encounters, checkinId, encounterData);
            log(`Encounter data fetched successfully for checkin ${checkinId}:`, encounterData);
            return encounterData;
        } catch (error) {
            console.error(`Error fetching encounter data for checkin ${checkinId}:`, error);
            return null;
        }
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
    
    function addToRecentSearches(searchTerm, patientData = null) {
        let recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        
        // Create a rich search object with more details
        const searchItem = {
            term: searchTerm,
            timestamp: new Date().toISOString(),
            patientId: patientData?.id || null,
            patientName: patientData ? formatPatientName(patientData.name) : null,
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
    function textToReportHtml(text) {
        return text.trim().split('\n').filter(Boolean).join('\n \n');
    }

    function displayPatientData(patientData) {
        log('Displaying patient data:', patientData);

        const name = formatPatientName(patientData.name);
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
            const [encounters, activeEncounters, presentations] = await Promise.all([
                limitedMap(checkoutIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchEncounterDataForCheckout(id); } catch (_) { return null; } }),
                limitedMap(checkinIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchEncounterDataForCheckin(id); } catch (_) { return null; } }),
                limitedMap(presentationIds, MAX_CONCURRENT_REQUESTS,
                    async id => { try { return await fetchPresentation(id); } catch (_) { return null; } })
            ]);

            // Build a unified list with type tags
            const encItems = encounters.filter(Boolean).map(enc => ({
                type: 'inpatient',
                enc,
                sortKey: enc.period?.end || enc.period?.start || '',
                start: enc.period?.start || '',
                end: enc.period?.end || '',
                label: extractDiagnosisText(enc) || 'No diagnosis recorded',
                section: enc.location?.[0]?.location?.display || '',
                medic: enc.participant?.[0]?.individual?.display || '',
                extra: '',
            }));

            // Active admissions (checked in, not yet discharged) — no end date yet.
            const activeItems = activeEncounters.filter(Boolean).map(enc => ({
                type: 'inpatient',
                enc,
                sortKey: enc.period?.start || '',
                start: enc.period?.start || '',
                end: '',
                label: extractDiagnosisText(enc) || 'No diagnosis recorded',
                section: enc.location?.[0]?.location?.display || '',
                medic: enc.participant?.[0]?.individual?.display || '',
                extra: '',
            }));

            const presItems = presentations.filter(Boolean).map(enc => {
                const start = enc.period?.start || '';
                const section = enc.location?.[0]?.location?.display || '';
                const reason = enc.reasonCode?.[0]?.text || '';
                const notes = enc.note || [];
                const decision = notes[0]?.text || '';
                const consultType = notes[1]?.text || '';
                const label = reason || consultType || 'Outpatient visit';
                return {
                    type: 'outpatient',
                    enc,
                    sortKey: start,
                    start: start ? formatDate(start) : '',
                    end: '',
                    label,
                    section,
                    medic: enc.participant?.[0]?.individual?.display || '',
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
        const name = formatPatientName(patientData.name);
        if (elements.patientName) elements.patientName.textContent = name;
        log('Patient name set to:', name);

        // Show who is loaded in the nav: "FAMILY G." instead of "Patient Profile"
        if (elements.navPatientLabel) {
            const n = Array.isArray(patientData.name) ? patientData.name[0] : patientData.name;
            const family = n?.family || '';
            const givenInitial = n?.given?.[0] ? ` ${n.given[0][0]}.` : '';
            elements.navPatientLabel.textContent = family ? `${family}${givenInitial}` : 'Patient Profile';
        }
        
        // Meta badges: ID · gender + age · diagnosis
        const age = calculateAge(patientData.birthDate);
        if (elements.patientId) {
            const pid = patientData.id || '';
            const patHipoUrl = (patientData.extension || []).find(e => e.url === 'hipocrateUrl')?.valueUri;
            elements.patientId.innerHTML = '';
            if (pid && patHipoUrl) {
                const a = document.createElement('a');
                a.href = patHipoUrl;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.textContent = `ID: ${pid}`;
                elements.patientId.appendChild(a);
            } else if (pid) {
                elements.patientId.textContent = `ID: ${pid}`;
            }
        }

        // Gender icon + age in one badge
        const genderIcon = patientData.gender === 'female' ? 'fa-venus' : patientData.gender === 'male' ? 'fa-mars' : null;
        const genderLabel = formatGender(patientData.gender);
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
        const cnp = extractCNP(patientData.identifier);
        if (elements.patientCnp)       elements.patientCnp.textContent       = cnp || '—';
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = formatBirthDate(patientData.birthDate) || '—';

        const contactInfo = extractContactInfo(patientData.telecom);
        if (elements.patientPhone) elements.patientPhone.textContent = contactInfo.phone || '—';
        if (elements.patientEmail) elements.patientEmail.textContent = contactInfo.email || '—';
        if (elements.patientAddress) {
            const addr = patientData.address?.[0];
            const text = addr?.text || '';
            const district = addr?.district || '';
            const display = district && !text.includes(district) ? `${text}, ${district}` : text;
            elements.patientAddress.textContent = display || '—';
        }
        log('CNP:', cnp, 'Phone:', contactInfo.phone, 'Email:', contactInfo.email);

        // QR codes
        const nameObj   = Array.isArray(patientData.name) ? patientData.name[0] : patientData.name;
        const lastName  = nameObj?.family || '';
        const firstName = nameObj?.given?.[0] || '';
        const birthDate = patientData.birthDate || '';
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

    function formatPatientName(nameArray) {
        if (!nameArray) return 'N/A';
        const arr = Array.isArray(nameArray) ? nameArray : [nameArray];
        if (arr.length === 0) return 'N/A';
        const name = arr[0];
        const family = name.family ? toTitleCase(name.family) : '';
        const given  = name.given  ? toTitleCase(name.given.join(' ')) : '';

        if (family && given) return `${family}, ${given}`;
        if (family) return family;
        if (given)  return given;
        return 'N/A';
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
    
    // Enhanced CNP extraction
    function extractCNP(identifierArray) {
        if (!identifierArray || !Array.isArray(identifierArray)) {
            return null;
        }
        
        const cnpIdentifier = identifierArray.find(id => 
            id.system && id.system.includes('cnp')
        );
        
        return cnpIdentifier ? cnpIdentifier.value : null;
    }
    
    // Enhanced contact info extraction
    function extractContactInfo(telecomArray) {
        const result = { phone: null, email: null };
        
        if (!telecomArray || !Array.isArray(telecomArray)) {
            return result;
        }
        
        const phone = telecomArray.find(t => t.system === 'phone');
        const email = telecomArray.find(t => t.system === 'email');
        
        result.phone = phone ? formatPhoneNumber(phone.value) : null;
        result.email = email ? email.value : null;
        
        return result;
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
    
    // Enhanced medical statistics extraction
    function extractMedicalStats(patientData) {
        const stats = {
            encounters: 0,
            admissions: 0,
            discharges: 0,
            checkoutIds: []
        };
        
        if (patientData.extension && Array.isArray(patientData.extension)) {
            const encounterExt = patientData.extension.find(ext =>
                ext.url && ext.url.includes('presentation-ids')
            );
            const admissionExt = patientData.extension.find(ext =>
                ext.url && ext.url.includes('checkin-ids')
            );
            const checkoutExt = patientData.extension.find(ext => 
                ext.url && ext.url.includes('checkout-ids')
            );
            
            if (encounterExt && encounterExt.valueString) {
                stats.encounters = encounterExt.valueString.split(',').filter(id => id.trim()).length;
            }
            
            if (admissionExt && admissionExt.valueString) {
                stats.admissions = admissionExt.valueString.split(',').filter(id => id.trim()).length;
            }
            
            if (checkoutExt && checkoutExt.valueString) {
                stats.checkoutIds = checkoutExt.valueString.split(',').filter(id => id.trim());
                stats.discharges = stats.checkoutIds.length;
            }
        }
        
        return stats;
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
            // Fetch imaging study data using FHIR API
            const studyResponse = await apiFetch(`/fhir/ImagingStudy/${studyId}`);
            
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
        if (studyData.started)
            addStudyInfoRow(studyInfo, 'fa-calendar', 'Started', formatDateWithTime(studyData.started));
        if (studyData.modality?.length > 0)
            addStudyInfoRow(studyInfo, 'fa-stethoscope', 'Modality', studyData.modality[0].display || studyData.modality[0].code || 'N/A');
        if (studyData.description)
            addStudyInfoRow(studyInfo, 'fa-file-medical', 'Description', studyData.description);
        if (studyData.performer?.length > 0)
            addStudyInfoRow(studyInfo, 'fa-user-md', 'Performer', studyData.performer[0].actor?.display || 'N/A');
        if (studyData.referrer)
            addStudyInfoRow(studyInfo, 'fa-user-check', 'Referrer', studyData.referrer.display || 'N/A');
        if (studyData.reason?.length > 0)
            addStudyInfoRow(studyInfo, 'fa-question-circle', 'Reason', studyData.reason[0].text || 'N/A');
        const notes = studyData.note || [];
        const indication = notes.find(n => n.category?.[0]?.text === 'clinical-indication');
        if (indication?.text)
            addStudyInfoRow(studyInfo, 'fa-notes-medical', 'Justificare', indication.text);
        const otherNote = notes.find(n => n !== indication);
        if (otherNote?.text)
            addStudyInfoRow(studyInfo, 'fa-sticky-note', 'Note', otherNote.text);
    }
    
    function populateSeriesList(seriesList, studyData) {
        if (!studyData.series || studyData.series.length === 0) return;
        const tmpl = document.getElementById('series-item-template');
        studyData.series.forEach((series, index) => {
            const li = tmpl.content.cloneNode(true).querySelector('li');
            li.querySelector('.series-label').textContent = `Series ${series.number || index + 1}:`;
            li.querySelector('.series-desc').textContent = series.description || 'N/A';
            const modalitySpan = li.querySelector('.series-modality');
            if (series.modality) {
                modalitySpan.textContent = ` (Modality: ${series.modality.display || series.modality.code || 'N/A'})`;
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
        const { grid, noData, eyebrow, eyebrowLabel, metaId, types } = ctx;

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
            const t = e.resource?.code?.coding?.[0]?.code || 'unknown';
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

        // Create cards immediately; lazily load report content as cards scroll into view
        const cards = entries.map(entry => {
            const sr = entry.resource;
            const type = sr.code?.coding?.[0]?.code || 'unknown';
            const text = sr.code?.coding?.[0]?.display || 'analysis';
            const card = createAnalysisCard(sr, type, text);
            grid.appendChild(card);
            return card;
        });

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
    // presentedForm entries buildLabTable renders, grouped by section. The
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

        // Group by analyte name, collect all measurements sorted by date
        const byAnalyte = {};
        for (const obs of observations) {
            const name = obs.code?.text;
            if (!name) continue;
            if (!byAnalyte[name]) {
                byAnalyte[name] = {
                    name,
                    unit: obs.valueQuantity?.unit || '',
                    low:  obs.referenceRange?.[0]?.low?.value  ?? null,
                    high: obs.referenceRange?.[0]?.high?.value ?? null,
                    ref:  obs.referenceRange?.[0]?.text || '',
                    measurements: [],
                };
            }
            byAnalyte[name].measurements.push({
                date: obs.effectiveDateTime || '',
                v:    obs.valueQuantity?.value ?? null,
                text: obs.valueString || null,
                flag: obs.interpretation?.[0]?.text || null,
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

        // All unique dates (oldest first) for column headers
        const allDates = [...new Set(observations.map(o => o.effectiveDateTime?.slice(0, 10)).filter(Boolean))].sort();
        const colDates = allDates.slice(-5);  // cap table at 5 most recent dates

        // Build table
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
        for (const a of analytes) {
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

        elements.trendsContainer.innerHTML = '';
        elements.trendsContainer.appendChild(table);
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
        const rows = abnormalAnalytes.map(a => {
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
            const name = `${a.name}${a.unit ? ' [' + a.unit + ']' : ''}`;
            return [name, interval, ...cells].join(' | ');
        });
        labHasAbnormal = abnormalAnalytes.length > 0;
        labAiText = labHasAbnormal ? [header, ...rows].join('\n') : '';
        if (elements.copyLabBtn) {
            elements.copyLabBtn.hidden = !labHasAbnormal;
            elements.trendsContainer.dataset.markdown = labHasAbnormal
                ? `# Lab Trends — Abnormal Analytes\n\n| ${header} |\n| ${header.split(' | ').map(() => '---').join(' | ')} |\n${rows.map(r => `| ${r} |`).join('\n')}`
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
    }

    async function loadTrends(patientId) {
        if (!patientId || !elements.trendsSection) return;
        const sd = new Date();
        sd.setDate(sd.getDate() - 90);
        const startDate = localDateStr(sd);
        try {
            const resp = await apiFetch(`/fhir/Observation?patient=${encodeURIComponent(patientId)}&start_date=${startDate}`);
            if (!resp.ok) return;
            const bundle = await resp.json();
            if (bundle.resourceType !== 'Bundle' || !bundle.entry?.length) return;
            renderTrends(bundle.entry.map(e => e.resource).filter(Boolean));
        } catch (e) {
            console.warn('Trends load failed:', e);
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

        article.className = `analysis-card ${analysisType}`;
        article.dataset.type = analysisType;
        article.dataset.serviceRequestId = serviceRequest.id;
        article.dataset.analysisType = analysisType;

        const modality = MODALITY_INFO[analysisType] || { icon: 'fa-file-medical', label: analysisText };
        // Modality circle avatar
        const circleEl = article.querySelector('.mod-circle');
        if (circleEl) {
            const circleAvatar = MODALITY_AVATAR[analysisType] || { icon: 'fa-question', cls: '' };
            circleEl.innerHTML = modAvatarHTML(analysisType);
            if (circleAvatar.cls) circleEl.classList.add(circleAvatar.cls);
        }

        const typeText = article.querySelector('.type-text');
        if (typeText) typeText.textContent = analysisText || modality.label;

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
        if (examDateEl && serviceRequest.authoredOn) {
            examDateEl.textContent = formatExamDate(serviceRequest.authoredOn);
            examDateEl.dateTime = serviceRequest.authoredOn;
        }

        // Body regions → part of the card title
        const regions = (serviceRequest.bodySite || [])
            .map(b => b.text).filter(Boolean);
        const regionsEl = article.querySelector('.card-regions');
        if (regionsEl && regions.length > 0) {
            regionsEl.textContent = ` · ${regions.join(', ')}`;
        }

        // Urgent badge
        if (serviceRequest.priority === 'urgent') {
            article.classList.add('urgent-card');
            const urgentEl = article.querySelector('.urgent-badge');
            if (urgentEl) urgentEl.hidden = false;
        }

        // Ordering physician (from ServiceRequest.requester)
        const referrer = serviceRequest.requester?.display;
        const referrerEl = article.querySelector('.card-referrer');
        if (referrerEl && referrer) {
            referrerEl.textContent = referrer;
            const line = article.querySelector('.card-referrer-line');
            if (line) line.hidden = false;
        }

        // Clinical indication — show inline next to physician
        const indication = serviceRequest.reason?.[0]?.display
            || serviceRequest.reasonCode?.[0]?.text
            || serviceRequest.reasonCode?.[0]?.coding?.[0]?.display;
        if (indication) {
            setCardIndication(article, indication);
        }

        // Remove write/validate controls from non-imaging cards immediately (type is known now)
        const IMAGING_TYPES_WRITE = ['radio', 'ct', 'irm', 'eco', 'rads'];
        if (!IMAGING_TYPES_WRITE.includes(analysisType)) {
            article.querySelector('.btn-write-report')?.remove();
            article.querySelector('.validate-toggles')?.remove();
        }

        return article;
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
            ? `/fhir/ImagingStudy/${id}`
            : `/fhir/DiagnosticReport/${id}`;

        const loadingEl = article.querySelector('.report-loading');
        const bodyEl    = article.querySelector('.report-body');

        // Reset report content before re-fetching so stale injected text doesn't duplicate
        article.querySelector('.report-preview')?.replaceChildren();
        article.classList.remove('no-report');
        // Reset the copy button; re-revealed below only when a report exists
        const cardCopyBtn = article.querySelector('.card-copy-btn');
        if (cardCopyBtn) { cardCopyBtn.hidden = true; cardCopyBtn.onclick = null; }
        // Reset the AI triage button; re-revealed only for imaging reports.
        // Also drop any card left over from a prior render of this article
        // (fetchAndFillReport can re-run via the perform/write refresh path).
        const cardAiBtn = article.querySelector('.card-ai-btn');
        if (cardAiBtn) { cardAiBtn.hidden = true; cardAiBtn._aiCard = null; }
        article.querySelector('.card-report-section .ai-summary-card')?.remove();

        let hasReportFromStudy = false;
        try {
            const resp = await apiFetch(endpoint);
            if (!resp.ok) throw new Error(resp.status);
            const data = await resp.json();

            // Ordering physician from referrer (if not already set from ServiceRequest)
            const referrerEl = article.querySelector('.card-referrer');
            if (referrerEl && !referrerEl.textContent && data.referrer?.display) {
                referrerEl.textContent = data.referrer.display;
                const line = article.querySelector('.card-referrer-line');
                if (line) line.hidden = false;
            }

            // Clinical indication note(s) → show inline next to physician
            const allNotes = data.note || [];
            const indicationNotes = allNotes.filter(n => n.category?.[0]?.text === 'clinical-indication');
            const resultNotes = allNotes.filter(n => n.category?.[0]?.text !== 'clinical-indication');
            if (indicationNotes.length > 0) {
                const existing = article.querySelector('.card-indication-text');
                if (!existing?.textContent) setCardIndication(article, indicationNotes[0].text);
            }

            // Report text
            const forms = data.presentedForm || [];
            const hasReport = forms.length > 0
                || resultNotes.some(n => n.text)
                || Boolean(data.conclusion);
            hasReportFromStudy = hasReport;

            // Store raw text so the editor modal can pre-populate
            if (canWriteReports) {
                const rawParts = forms.length > 0
                    ? forms.filter(f => f.data && !f.reference).map(f => f.data)
                    : resultNotes.filter(n => n.text).map(n => n.text);
                if (rawParts.length === 0 && data.conclusion) rawParts.push(data.conclusion);
                article.dataset.reportText = rawParts.join('\n\n');
            }

            // Signature footer only when a report actually exists — without one,
            // performer falls back to the requesting physician server-side and
            // showing it here would misattribute the (nonexistent) report
            if (hasReport) {
                const physician = data.resultsInterpreter?.[0]?.display
                    || data.performer?.[0]?.actor?.display || '';
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
                    const series = data.series || [];
                    const showTitles = series.length >= notes.length;
                    notes.forEach((note, i) => {
                        if (!note.text) return;
                        if (showTitles && series[i]?.description) {
                            const titleEl = document.createElement('p');
                            titleEl.className = 'series-result-title';
                            titleEl.textContent = series[i].description;
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
                        .map((note, i) => {
                            if (!note.text) return '';
                            const t = (showTitles && series[i]?.description) ? `##### ${series[i].description}\n\n` : '';
                            return t + note.text.trim();
                        })
                        .filter(Boolean)
                        .join('\n\n');
                } else if (data.conclusion) {
                    const div = document.createElement('div');
                    div.innerHTML = marked.parse(data.conclusion);
                    reportPreview.appendChild(div);
                    copyMd = data.conclusion.trim();
                } else {
                    article.classList.add('no-report');
                }
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
                // report, if any (mirrors lab/epicrisis/report/pre_exam).
                runAiSummary(
                    cardAiBtn, 'imaging',
                    () => article.querySelector('.report-body'),
                    () => cardAiBtn.dataset.aiText || '',
                    { inline: true, auto: true });
                enqueueAiWarm('imaging', copyMd, dataGeneration);
            }

            // ImagingStudy link
            const imagingStudyLink = article.querySelector('.imaging-study-link');
            if (imagingStudyLink && data.imagingStudy) {
                const studyId = data.imagingStudy.reference.split('/')[1];
                const linkTmpl = document.getElementById('imaging-study-link-template');
                if (linkTmpl) {
                    const a = linkTmpl.content.cloneNode(true).querySelector('a');
                    a.querySelector('.study-ref-id').textContent = `#${studyId}`;
                    a.addEventListener('click', e => { e.preventDefault(); viewImagingStudy(studyId, id); });
                    imagingStudyLink.appendChild(a);
                }
            }
        } catch (_) {
            article.classList.add('no-report');
        } finally {
            if (loadingEl) loadingEl.hidden = true;
            if (bodyEl) bodyEl.hidden = false;
            // Show write/validate buttons for imaging types once canWriteReports is resolved
            await whoamiReady;
            if (canWriteReports) {
                const writeBtn = article.querySelector('.btn-write-report');
                const performBtn = article.querySelector('.btn-perform-exam');
                if (writeBtn) writeBtn.hidden = true;
                if (performBtn) performBtn.hidden = true;
                const togglesElReset = article.querySelector('.validate-toggles');
                if (togglesElReset) { togglesElReset.hidden = true; togglesElReset.replaceChildren(); }
                // write button is shown after cerere fetch confirms editable analyses exist
                // Fetch cerere.asp state: report text (may be unvalidated) + per-analysis validate toggles
                const cerereId = article.dataset.serviceRequestId;
                try {
                    const r = await fetch(`/api/request/${cerereId}/patient`, { headers: authHeader() });
                    const d = await r.json();
                    const analyses = Array.isArray(d.report) ? d.report
                        : (d.report && typeof d.report === 'object' ? [d.report] : []);
                    // Store for editor
                    article.dataset.reportAnalyses = JSON.stringify(analyses);

                    // Show unvalidated report text if BuletinAnalize had nothing yet
                    const previewEl = article.querySelector('.report-preview');
                    if (previewEl && !previewEl.textContent.trim()) {
                        const withText = analyses.filter(a => a.text);
                        if (withText.length) {
                            const showTitles = withText.length > 1 || withText[0]?.label;
                            for (const a of withText) {
                                if (showTitles && a.label) {
                                    const titleEl = document.createElement('p');
                                    titleEl.className = 'series-result-title';
                                    titleEl.textContent = a.label;
                                    previewEl.appendChild(titleEl);
                                }
                                const div = document.createElement('div');
                                div.className = 'report-note';
                                div.innerHTML = a.text;
                                previewEl.appendChild(div);
                            }
                            article.classList.remove('no-report');
                        }
                    }

                    const hasReport    = analyses.some(a => a.text);
                    const isEditable   = analyses.some(a => a.editable);
                    const allValidated = analyses.length > 0 && analyses.every(a => a.validated);
                    // Treat as performed if: DataEfectuarii set, all cerere analyses validated,
                    // or BuletinAnalize already has a published report (cerere.asp may not render
                    // fn_validate_cerere calls once the exam is fully finalised in Hipocrate)
                    const performed    = Boolean(d.performed_at) || allValidated || hasReportFromStudy;

                    if (performed) article.classList.remove('no-report');

                    // State 1: not performed → perform button only
                    if (performBtn && !performed) {
                        performBtn.hidden = false;
                        performBtn.replaceWith(performBtn.cloneNode(true));
                        article.querySelector('.btn-perform-exam')
                            .addEventListener('click', () => markExamPerformed(article, cerereId));
                    }

                    // States 2 & 3: performed + editable + not fully validated → write button
                    if (writeBtn && performed && isEditable && !allValidated) {
                        writeBtn.hidden = false;
                        writeBtn.replaceWith(writeBtn.cloneNode(true));
                        article.querySelector('.btn-write-report')
                            .addEventListener('click', () => openReportEditor(article));
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

                            // Inject into matching series-result-title, fall back to validate-toggles row
                            const titleEl = previewTitles.find(t => t.firstChild?.textContent?.trim() === analysis.label?.trim())
                                ?? previewTitles[i];
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
            body: JSON.stringify({}),
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
        await markExamPerformedCore(cerereId, {
            setDisabled: (v) => { if (btn) btn.disabled = v; },
            onDone: () => fetchAndFillReport(article)
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

        const now = new Date();
        const idEl = modal.querySelector('.editor-report-id');
        if (idEl) idEl.textContent = `#${cerereId}`;
        const dateEl = modal.querySelector('.editor-report-date');
        if (dateEl) dateEl.textContent =
            `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

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
                    const html = textToReportHtml(text);
                    const resp = await apiFetch(`/api/request/${cerereId}/report`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ anl_id, text: html }),
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
    
    function extractCheckoutIds(patientData) {
        if (!patientData.extension) return [];
        const checkoutExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkout-ids'));
        if (!checkoutExt || !checkoutExt.valueString) return [];
        return checkoutExt.valueString.split(',').filter(id => id.trim());
    }

    function extractCheckinIds(patientData) {
        if (!patientData.extension) return [];
        const checkinExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkin-ids'));
        if (!checkinExt || !checkinExt.valueString) return [];
        return checkinExt.valueString.split(',').filter(id => id.trim());
    }

    function extractPresentationIds(patientData) {
        if (!patientData.extension) return [];
        const ext = patientData.extension.find(e => e.url && e.url.includes('presentation-ids'));
        if (!ext || !ext.valueString) return [];
        return ext.valueString.split(',').filter(id => id.trim());
    }

    async function fetchPresentation(id) {
        if (cache.encounters[id]) return cache.encounters[id];
        const response = await apiFetch(`/fhir/Encounter/${id}?type=presentation`);
        if (!response.ok) return null;
        const data = await response.json();
        if (data.resourceType !== 'Encounter') return null;
        cachePut(cache.encounters, id, data);
        return data;
    }

    function extractEpicrisisText(encounterData) {
        if (!encounterData.note || !Array.isArray(encounterData.note)) return '';
        return encounterData.note.map(note => note.text || '').join('\n\n');
    }

    // Returns true if text has meaningful content beyond markdown markers and punctuation.
    function isSubstantiveText(text) {
        return /[a-zA-ZÀ-žА-я0-9]/.test(text || '');
    }

    // 72-hour (revised) diagnosis and secondary-diagnosis/comorbidity list from
    // a checkin encounter's diagnosis[] array — populated by fhir_response()
    // alongside the admission diagnosis (role codes 'working' and 'CC').
    function extract72hDiagnosisText(enc) {
        return (enc.diagnosis || []).find(d => d.use?.coding?.some(c => c.code === 'working'))
            ?.condition?.display || null;
    }
    function extractSecondaryDiagnoses(enc) {
        return (enc.diagnosis || [])
            .filter(d => d.use?.coding?.some(c => c.code === 'CC'))
            .map(d => d.condition?.display)
            .filter(Boolean);
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
        (enc.note || []).forEach(n => {
            if (!n.text) return;
            const clean = n.text.replace(/^\[Exam general\]\s*/i, '').replace(/^\[Exam local\]\s*/i, '').trim();
            if (clean) parts.push(clean);
        });
        return parts.join('\n\n');
    }

    async function loadAndDisplayEpicrisis(patientData) {
        const checkoutIds = extractCheckoutIds(patientData);
        // Fetch every checkin id, not just ones without a matching checkout id — a
        // genuinely ongoing admission (e.g. ICU, no discharge summary yet) needs its
        // "in-progress" status checked against actual checkout dates, not just id
        // membership (a checkin's status never flips once the patient is discharged).
        const checkinIds = extractCheckinIds(patientData);
        if (checkoutIds.length === 0 && checkinIds.length === 0) {
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
                const da = a.enc.period?.end || '';
                const db = b.enc.period?.end || '';
                return db > da ? 1 : -1;
            });

        // A checkin's "in-progress" status is a scrape artifact that never updates
        // once the patient is discharged, so treat it as genuinely active only if
        // it starts after every known checkout has already concluded.
        const latestCheckoutEnd = checkoutEncounters
            .filter(Boolean)
            .reduce((latest, enc) => {
                const end = enc.period?.end || enc.period?.start || '';
                return end > latest ? end : latest;
            }, '');
        const activeEnc = checkinEncounters
            .map((enc, i) => enc ? { enc, checkinId: checkinIds[i] } : null)
            .filter(item => item && item.enc.status === 'in-progress' &&
                (!latestCheckoutEnd || (item.enc.period?.start || '') > latestCheckoutEnd))
            .sort((a, b) => (b.enc.period?.start || '').localeCompare(a.enc.period?.start || ''))[0];

        // Ongoing admission always shown first, ahead of past discharges — with
        // diagnosis/exam text as a fallback body when epicrisis hasn't been
        // written yet (it's normally only filled in near/at discharge).
        if (activeEnc) {
            valid.unshift({ enc: activeEnc.enc, checkoutId: activeEnc.checkinId, active: true, fallbackBody: buildCheckinBody(activeEnc.enc) });
        }

        if (valid.length === 0) {
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
        let markdown = '';
        valid.forEach((item, index) => {
            const enc = item.enc;
            // Ongoing admissions rarely have epicrisis text yet (it's normally only
            // written near/at discharge) — fall back to diagnosis + exam notes so the
            // current admission still shows up instead of being silently dropped.
            const epicrisisText = extractEpicrisisText(enc) || item.fallbackBody || '';
            const icd = extractDiagnosisText(enc) || '';
            const admission = enc.period?.start ? formatDate(enc.period.start) : '';
            const discharge = enc.period?.end ? formatDate(enc.period.end) : '';
            const service = enc.serviceType?.display || '';
            const ward = enc.location?.slice(-1)[0]?.location?.display || '';
            const attender = enc.participant?.find(p =>
                p.type?.some(t => t.coding?.some(c => c.code === 'ATND'))
            )?.individual?.display || '';

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
            if (item.active) card.classList.add('epi-card--active');
            card.id = `epicrisis-${item.checkoutId}`;
            card.dataset.markdown = `# ${heading}\n\n`
                + (meta.length ? `${meta.join(' · ')}  \n\n` : '')
                + epicrisisText.trim() + '\n';

            const btn    = card.querySelector('.epi-card-btn');
            const body   = card.querySelector('.epi-card-body');
            const chevron = card.querySelector('.epi-chevron');

            btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            card.querySelector('.epi-date-range').textContent = item.active ? `${admission} → Present` : `${admission} → ${discharge}`;
            const serviceParts = [ward, attender].filter(Boolean);
            card.querySelector('.epi-service').textContent = serviceParts.length ? serviceParts.join(' · ') : (service || 'Admission');

            const icdBadge = card.querySelector('.epi-icd-badge');
            if (icd) { icdBadge.textContent = icd; } else { icdBadge.remove(); }
            const nightsSpan = card.querySelector('.epi-nights');
            if (item.active) { nightsSpan.textContent = 'Ongoing'; nightsSpan.classList.add('epi-nights--active'); }
            else if (nights) { nightsSpan.textContent = nights; }
            else { nightsSpan.remove(); }
            if (isOpen) chevron.className = 'fas fa-chevron-up epi-chevron';

            body.hidden = !isOpen;
            const copyBtn = card.querySelector('.epi-copy-btn');
            const aiBtn = card.querySelector('.epi-ai-btn');
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
                prose.classList.add('epi-prose--empty');
                card.querySelector('.card-toolbar').hidden = true;
            }

            btn.addEventListener('click', () => {
                const open = card.classList.toggle('epi-card-open');
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
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
    let activeScheduleStatusFilter = '';

    async function showRequestModal(requestId, requestCode, patientName, modality, triggerEl, requesterName) {
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

        const originalText = triggerEl.textContent;
        triggerEl.textContent = '…';
        triggerEl.disabled = true;

        function renderReportContent(reportData, isImaging) {
            bodyDiv.innerHTML = '';
            bodyDiv.classList.remove('report-empty');
            const forms = reportData.presentedForm || [];
            const allNotes = reportData.note || [];
            const resultNotes = allNotes.filter(n => n.category?.[0]?.text !== 'clinical-indication');
            const series = reportData.series || [];

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
                const showTitles = resultNotes.length > 1 && series.length >= resultNotes.length;
                resultNotes.forEach((note, i) => {
                    if (!note.text) return;
                    if (showTitles && series[i]?.description) {
                        const titleEl = document.createElement('p');
                        titleEl.className = 'series-result-title';
                        titleEl.textContent = series[i].description;
                        bodyDiv.appendChild(titleEl);
                    }
                    const div = document.createElement('div');
                    div.className = 'report-note';
                    const normalised = note.text.replace(/\n{2,}/g, '\n');
                    div.innerHTML = marked.parse(normalised).trim();
                    bodyDiv.appendChild(div);
                });
            } else if (reportData.conclusion) {
                bodyDiv.innerHTML = marked.parse(reportData.conclusion);
            } else {
                bodyDiv.classList.add('report-empty');
            }
        }

        // Wire up close / load buttons before showing
        modal.querySelector('.report-modal-close').addEventListener('click', () => modal.close());
        modal.querySelector('[data-close-modal]').addEventListener('click', () => modal.close());
        modal.addEventListener('close', () => document.body.removeChild(modal));
        modal.querySelector('.modal-load-patient-btn').addEventListener('click', () => {
            modal.close();
            loadPatientFromRequest(requestId, patientName, triggerEl);
        });

        bodyDiv.classList.add('report-empty');
        bodyDiv.textContent = 'Loading…';
        document.body.appendChild(modal);
        modal.showModal();

        const imagingTypes = ['radio', 'ct', 'irm', 'eco', 'rads', 'fluoro'];
        const isImaging = imagingTypes.includes(modality);

        async function loadAndRenderReport() {
            const endpoint = isImaging
                ? `/fhir/ImagingStudy/${requestId}`
                : `/fhir/DiagnosticReport/${requestId}`;

            const repResp = await apiFetch(endpoint);
            if (repResp.ok) {
                const reportData = await repResp.json();

                // Date in subtitle
                const date = reportData.started || reportData.effectiveDateTime || reportData.authoredOn;
                if (date) modal.querySelector('.modal-date').textContent = formatDateWithTime(date);

                // Requester fallback from report data if not passed from schedule row
                if (!requesterName) {
                    const requester = reportData.referrer?.display;
                    if (requester) {
                        modal.querySelector('.modal-requester').textContent = requester;
                        modal.querySelector('.report-modal-referrer').hidden = false;
                    }
                }

                // Indication line in header
                const allNotes = reportData.note || [];
                const indicationNote = allNotes.find(n => n.category?.[0]?.text === 'clinical-indication');
                if (indicationNote?.text) {
                    modal.querySelector('.modal-indication-text').textContent = indicationNote.text;
                    modal.querySelector('.report-modal-indication').hidden = false;
                }

                // Examiner (reporting physician) appended below content — only
                // when a report actually exists. Without one, performer falls
                // back to the requesting physician server-side, so showing it
                // here would misattribute a report that doesn't exist yet
                // (same guard the Imaging tab cards use, scripts.js:2995-3006).
                const examiner = reportData.resultsInterpreter?.[0]?.display
                    || reportData.performer?.[0]?.actor?.display;

                renderReportContent(reportData, isImaging);
                const hasReport = !bodyDiv.classList.contains('report-empty');

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
            try {
                const r = await fetch(`/api/request/${requestId}/patient`, { headers: authHeader() });
                const d = await r.json();
                const analyses = Array.isArray(d.report) ? d.report
                    : (d.report && typeof d.report === 'object' ? [d.report] : []);
                const hasReport    = analyses.some(a => a.text);
                const isEditable   = analyses.some(a => a.editable);
                const allValidated = analyses.length > 0 && analyses.every(a => a.validated);
                const performed    = Boolean(d.performed_at) || allValidated;

                // If nothing rendered yet (report not validated/published), show
                // the freshly-entered cerere text directly — same fallback the
                // Imaging tab cards use, so a just-saved report doesn't read as
                // "not yet available".
                if (bodyDiv.classList.contains('report-empty')) {
                    const withText = analyses.filter(a => a.text);
                    if (withText.length) {
                        bodyDiv.innerHTML = '';
                        bodyDiv.classList.remove('report-empty');
                        const showTitles = withText.length > 1 || withText[0]?.label;
                        for (const a of withText) {
                            if (showTitles && a.label) {
                                const titleEl = document.createElement('p');
                                titleEl.className = 'series-result-title';
                                titleEl.textContent = a.label;
                                bodyDiv.appendChild(titleEl);
                            }
                            const div = document.createElement('div');
                            div.className = 'report-note';
                            div.innerHTML = a.text;
                            bodyDiv.appendChild(div);
                        }
                    }
                }

                // Perform button — clone-and-replace to drop stale listeners
                // from a previous refresh (same trick fetchAndFillReport uses).
                let performBtn = modal.querySelector('.btn-perform-exam');
                if (performBtn) {
                    performBtn.replaceWith(performBtn.cloneNode(true));
                    performBtn = modal.querySelector('.btn-perform-exam');
                    performBtn.hidden = performed;
                    if (!performed) {
                        performBtn.addEventListener('click', () => {
                            markExamPerformedCore(requestId, {
                                setDisabled: v => { performBtn.disabled = v; },
                                onDone: refreshAll
                            });
                        });
                    }
                }

                // Edit Report button
                let editBtn = modal.querySelector('.btn-edit-report');
                if (editBtn) {
                    editBtn.replaceWith(editBtn.cloneNode(true));
                    editBtn = modal.querySelector('.btn-edit-report');
                    const showEdit = performed && isEditable && !allValidated;
                    editBtn.hidden = !showEdit;
                    if (showEdit) {
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
        triggerEl.textContent = originalText;
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
            const resp = await apiFetch(`/fhir/ImagingStudy/${requestId}`);
            if (resp.ok) {
                const json = await resp.json();
                const ref = json.subject?.reference || '';
                const patientId = ref.startsWith('Patient/') ? ref.slice(8) : null;
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
        const limit       = elements.scheduleLimitSelect?.value || null;
        fetchSchedule(start, end, force, patientText, labId, sectionName, limit);
    }

    async function fetchSchedule(startDate, endDate, force = false, patientText = null, labId = null, sectionName = null, limit = null) {
        if (!elements.scheduleBody) return;
        const params = new URLSearchParams();
        if (startDate)   params.set('start_date', startDate);
        if (endDate)     params.set('end_date', endDate);
        if (force)       params.set('refresh', '1');
        if (patientText) params.set('patient_text', patientText);
        if (labId)       params.set('lab_id', labId);
        if (sectionName) params.set('section_name', sectionName);
        if (limit)       params.set('limit', limit);
        const url = `/fhir/Schedule${params.toString() ? '?' + params.toString() : ''}`;
        if (elements.noSchedule) elements.noSchedule.style.display = 'none';
        showLoading('Loading schedule…');
        try {
            const resp = await apiFetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const bundle = await resp.json();
            scheduleEntries = (bundle.entry || []).map(e => e.resource);
            // Repopulate section dropdown only when not currently filtered by section
            if (!sectionName) populateSectionFilter(scheduleEntries);
            renderSchedule();
            if (elements.scheduleTable) elements.scheduleTable.dataset.loaded = '1';
        } catch (err) {
            showToast(`Failed to load schedule: ${err.message}`, 'error');
        } finally {
            hideLoading();
        }
    }

    function updateWardPillLabel() {
        const sel = elements.scheduleSectionFilter;
        if (!sel) return;
        const pill = sel.closest('.schedule-ward-pill');
        if (!pill) return;
        let label = pill.querySelector('.ward-label');
        if (!label) {
            label = document.createElement('span');
            label.className = 'ward-label';
            // insert between the two icons
            const chevron = pill.querySelector('.fa-chevron-down');
            pill.insertBefore(label, chevron);
        }
        label.textContent = sel.value
            ? sel.options[sel.selectedIndex]?.text || 'All wards'
            : 'All wards';
    }

    function populateSectionFilter(entries) {
        if (!elements.scheduleSectionFilter) return;
        const sections = [...new Set(entries.map(r => r.note?.[0]?.text || '').filter(Boolean))].sort();
        const current = elements.scheduleSectionFilter.value;
        elements.scheduleSectionFilter.innerHTML = '<option value="">All wards</option>';
        sections.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            if (s === current) opt.selected = true;
            elements.scheduleSectionFilter.appendChild(opt);
        });
        updateWardPillLabel();
    }

    function renderSchedule() {
        const container = elements.scheduleTimeline || elements.scheduleBody;
        if (!container) return;

        container.innerHTML = '';

        const visibleEntries = activeScheduleStatusFilter
            ? scheduleEntries.filter(r => r.status === activeScheduleStatusFilter)
            : scheduleEntries;

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
            const authoredOn = r.authoredOn || '';
            const hasTime = authoredOn.includes(' ');
            const day = hasTime ? authoredOn.split(' ')[0] : authoredOn;
            const time = hasTime ? authoredOn.split(' ')[1] : '';

            const patientName = r.subject?.display || '';
            const requestCode = r.identifier?.[0]?.value || r.id || '';
            const section = r.note?.[0]?.text || '';
            const requestedBy = r.requester?.display || '';
            const laboratory = r.code?.text || '';
            const modalitySlug  = r.category?.[0]?.coding?.[0]?.code || '';
            const paymentSlug   = r.category?.[1]?.coding?.[0]?.code || '';
            const status = r.status || '';
            const statusClass = SCHEDULE_STATUS_CLASS[status] || '';
            const isUrgent = r.priority === 'urgent';
            const avatar = MODALITY_AVATAR[modalitySlug] || { icon: 'fa-question', cls: '' };
            const isLast = idx === visibleEntries.length - 1;

            // Day group heading
            if (isMultiDay && day && day !== currentDay) {
                currentDay = day;
                const heading = document.createElement('p');
                heading.className = 'timeline-day-heading';
                heading.textContent = formatDayHeading(day);
                container.appendChild(heading);
            }

            // Row: time col + card
            const row = document.importNode(document.getElementById('timeline-row-template').content, true).firstElementChild;
            if (modalitySlug) row.dataset.modality = modalitySlug;

            // Time column
            const timeEl = row.querySelector('.timeline-time');
            timeEl.dateTime = authoredOn.replace(' ', 'T');
            timeEl.textContent = isMultiDay ? (time || day) : (time || authoredOn);

            const dot = row.querySelector('.timeline-dot');
            if (avatar.cls) dot.classList.add(avatar.cls);
            if (isLast) row.querySelector('.timeline-line').remove();

            // Card
            const card = row.querySelector('.timeline-card');
            if (isUrgent) card.classList.add('urgent-ring');

            const avatarEl = row.querySelector('.timeline-mod-avatar');
            if (avatar.cls) avatarEl.classList.add(avatar.cls);
            avatarEl.innerHTML = modAvatarHTML(modalitySlug);
            avatarEl.title = MODALITY_INFO[modalitySlug]?.label || laboratory || modalitySlug;

            const nameBtn = row.querySelector('.timeline-card-patient');
            nameBtn.textContent = patientName;
            nameBtn.title = `Load patient record for ${patientName}`;
            nameBtn.addEventListener('click', () => loadPatientFromRequest(r.id, patientName, nameBtn));

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
            regionLine.dataset.requestId = r.id;
            regionLine.dataset.modality = laboratory;

            // Meta line: hide unused parts
            const metaSectionEl  = row.querySelector('.timeline-meta-section');
            const metaRequesterEl = row.querySelector('.timeline-meta-requester');
            const seps = row.querySelectorAll('.timeline-meta-sep');
            if (section) {
                metaSectionEl.querySelector('span').textContent = section;
            } else {
                metaSectionEl.remove();
                seps[0]?.remove();
            }
            if (requestedBy) {
                metaRequesterEl.querySelector('span').textContent = requestedBy;
            } else {
                metaRequesterEl.remove();
                seps[1]?.remove();
            }

            const codeBtn = row.querySelector('.timeline-code');
            codeBtn.textContent = requestCode;
            codeBtn.title = `View request details (${requestCode})`;
            codeBtn.addEventListener('click', () => showRequestModal(r.id, requestCode, patientName, modalitySlug, codeBtn, requestedBy));
            const numericIdEl = row.querySelector('.timeline-numeric-id');
            if (hipocrateUrl) {
                const idLink = document.createElement('a');
                idLink.href = `${hipocrateUrl}/PARA/NOM/Listare/cerere.asp?id=${r.id}`;
                idLink.target = '_blank';
                idLink.rel = 'noopener noreferrer';
                idLink.textContent = `#${r.id}`;
                numericIdEl.appendChild(idLink);
            } else {
                numericIdEl.textContent = `#${r.id}`;
            }

            const statusBadge = row.querySelector('.timeline-status-badge');
            if (statusClass) statusBadge.classList.add(statusClass);
            statusBadge.textContent = SCHEDULE_STATUS_LABEL[status] || status;
            statusBadge.title = status;

            container.appendChild(row);
            scheduleExamObserver.observe(regionLine);
        });

        if (elements.scheduleTable) elements.scheduleTable.hidden = false;
    }

    // Filters placeholder junk like ". .. ." that doctors sometimes type just to pass form validation
    function _isMeaningfulText(text) {
        return !!text && /[A-Za-z0-9À-ɏ]/.test(text);
    }

    // Intersection observer: fetch exam names from cerere when card scrolls into view
    const _examCache = {};
    const scheduleExamObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const el = entry.target;
            scheduleExamObserver.unobserve(el);
            const id = el.dataset.requestId;
            if (!id) return;
            if (_examCache[id]) { _applyExamLabel(el, _examCache[id]); return; }
            apiFetch(`/fhir/ImagingStudy/${id}`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    const regions = _extractRegions(data);
                    // Backend already applies comment > justification priority (filtering
                    // placeholder junk) and falls back to reason (diagnosis) when neither exist.
                    const noteIndication = (data?.note || []).find(n => n.category?.[0]?.text === 'clinical-indication')?.text || '';
                    const indication = _isMeaningfulText(noteIndication) ? noteIndication : (data?.reason?.[0]?.text || '');
                    if (regions.length || indication) {
                        _examCache[id] = { regions, indication };
                        _applyExamLabel(el, _examCache[id]);
                        return;
                    }
                    // Study not yet reported — fall back to ServiceRequest for ordered procedure
                    // regions, plus the cerere.asp variant (only source of Justificare text)
                    return Promise.all([
                        apiFetch(`/fhir/ServiceRequest/${id}`).then(r => r.ok ? r.json() : null),
                        apiFetch(`/fhir/ServiceRequest/${id}?type=cerere`).then(r => r.ok ? r.json() : null)
                    ]).then(([d, cerere]) => {
                        // Priority: doctor's comment (buletinRecoltari) > justification (cerere) > diagnosis
                        // — placeholder junk (e.g. ". .. .") is treated as absent.
                        const commentIndication = (d?.note || []).find(n => n.category?.[0]?.text === 'clinical-indication')?.text || '';
                        const cerereIndication = (cerere?.note || []).find(n => n.category?.[0]?.text === 'clinical-indication')?.text || '';
                        const diagnosis = cerere?.reason?.[0]?.display || d?.reason?.[0]?.display || '';
                        const indication = [commentIndication, cerereIndication, diagnosis].find(_isMeaningfulText) || '';
                        const cached = { regions: _extractRegions(d), indication };
                        _examCache[id] = cached;
                        _applyExamLabel(el, cached);
                    });
                })
                .catch(() => {});
        });
    }, { rootMargin: '200px' });

    function _extractRegions(resource) {
        // ImagingStudy: series[].bodySite.display
        if (resource?.series) {
            const regions = [...new Set(
                resource.series
                    .map(s => s.bodySite?.display)
                    .filter(Boolean)
            )];
            if (regions.length) return regions;
        }
        // ServiceRequest: bodySite[].text
        if (resource?.bodySite) {
            return [...new Set(resource.bodySite.map(b => b.text).filter(Boolean))];
        }
        return [];
    }

    function _applyExamLabel(el, { regions, indication }) {
        el.innerHTML = '';
        const modality = el.dataset.modality || '';
        const regionText = regions.length
            ? regions.join(', ') + (modality ? ' · ' + modality : '')
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
        const urgent    = scheduleEntries.filter(r => r.priority === 'urgent').length;
        const inLab     = scheduleEntries.filter(r => ['draft', 'active'].includes(r.status)).length;
        const completed = scheduleEntries.filter(r => ['completed', 'ended'].includes(r.status)).length;

        const metricDefs = [
            { label: 'Exams',     value: total,     color: 'var(--text, #0f172a)' },
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
                const slug = r.category?.[0]?.coding?.[0]?.code || 'other';
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
        if (!encounterData.diagnosis || encounterData.diagnosis.length === 0) return null;
        const dd = encounterData.diagnosis.find(d =>
            d.use?.coding?.some(c => c.code === 'DD')
        );
        return dd?.condition?.display
            || encounterData.diagnosis[0]?.condition?.display
            || null;
    }

});
