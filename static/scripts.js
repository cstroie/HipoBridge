marked.use({ breaks: true });

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements - Cache selectors for better performance
    const elements = {
        form: document.getElementById('cnpForm'),
        cnpInput: document.getElementById('cnpInput'),
        analyzeBtn: document.getElementById('analyzeBtn'),
        errorDiv: document.getElementById('error'),
        backToSearchBtn: document.getElementById('backToSearch'),
        navItems: document.querySelectorAll('.nav-item'),
        tabContents: document.querySelectorAll('.tab-content'),
        // Patient tab elements
        patientId: document.getElementById('patientId'),
        patientAvatar: document.querySelector('.patient-avatar i'),
        patientName: document.getElementById('patientName'),
        patientCnp: document.getElementById('patientCnp'),
        patientGender: document.getElementById('patientGender'),
        patientDiagnosis: document.getElementById('patientDiagnosis'),
        patientBirthDate: document.getElementById('patientBirthDate'),
        patientPhone: document.getElementById('patientPhone'),
        patientEmail: document.getElementById('patientEmail'),
        patientAddress: document.getElementById('patientAddress'),
        navPatientLabel: document.getElementById('navPatientLabel'),
        navPatientGroup: document.getElementById('navPatientGroup'),
        historyList: document.getElementById('historyList'),
        historyLoading: document.getElementById('historyLoading'),
        historyEmpty: document.getElementById('historyEmpty'),
        presentationsCount: document.getElementById('presentationsCount'),
        checkinsCount: document.getElementById('checkinsCount'),
        checkoutsCount: document.getElementById('checkoutsCount'),
        reportsCount: document.getElementById('reportsCount'),
        // Analyses tab elements
        analysesGrid: document.getElementById('analysesGrid'),
        noAnalyses: document.getElementById('noAnalyses'),
        // Epicrisis tab elements
        epicrisisContent: document.getElementById('epicrisisContent'),
        epicrisisNav: document.getElementById('epicrisisNav'),
        copyEpicrisisBtn: document.getElementById('copyEpicrisisBtn'),
        // Report tab elements
        patientReportMarkdown: document.getElementById('patientReportMarkdown'),
        copyReportBtn: document.getElementById('copyReportBtn'),
        // Header elements
        quickSearch: document.getElementById('quickSearch'),
        quickSearchBtn: document.getElementById('quickSearchBtn'),
        themeToggle: document.getElementById('themeToggle'),
        userButton: document.getElementById('userButton'),
        // Search examples
        clearRecentBtn: document.getElementById('clearRecentBtn'),
        recentEmpty: document.getElementById('recentEmpty'),
        // Patient actions
        // Analyses actions
        analysesSearch: document.getElementById('analysesSearch'),
        analysesFilter: document.getElementById('analysesFilter'),
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
        scheduleCount: document.getElementById('scheduleCount'),
        scheduleLoading: document.getElementById('scheduleLoading'),
        noSchedule: document.getElementById('noSchedule'),
        scheduleTimeline: document.getElementById('scheduleTimeline'),
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

    // Initialize application
    initApp();
    
    function initApp() {
        // Initialize theme
        initTheme();
        
        // Initialize tabs
        initializeTabs();
        
        // Initialize event listeners
        initEventListeners();
        
        // Load recent searches
        loadRecentSearches();
        
    }
    
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'auto';
        document.documentElement.setAttribute('data-theme', savedTheme);
        const themeIcon = elements.themeToggle?.querySelector('i');
        if (themeIcon) themeIcon.className = savedTheme === 'dark' ? 'fas fa-sun' : savedTheme === 'light' ? 'fas fa-moon' : 'fas fa-circle-half-stroke';
    }
    
    function initializeTabs() {
        // Set schedule date defaults before switchTab triggers the first fetch
        const today = new Date().toISOString().slice(0, 10);
        const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
        if (elements.scheduleStartDate) elements.scheduleStartDate.value = yesterday;
        if (elements.scheduleEndDate)   elements.scheduleEndDate.value   = today;

        elements.tabContents.forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });

        // Honour the URL fragment, but only for tabs available without a
        // loaded patient; patient-scoped tabs fall back to the default
        const hash = location.hash.replace('#', '');
        switchTab(['schedule', 'search'].includes(hash) ? hash : 'schedule');
    }
    
    function initEventListeners() {
        // Tab navigation
        elements.navItems.forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                switchTab(this.getAttribute('data-tab'));
            });
        });
        
        // Back to search button
        if (elements.backToSearchBtn) {
            elements.backToSearchBtn.addEventListener('click', function() {
                elements.form.reset();
                clearResults();
                switchTab('search');
            });
        }
        
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

        // Analyses search and filter
        if (elements.analysesSearch) {
            elements.analysesSearch.addEventListener('input', filterAnalyses);
        }
        
        if (elements.analysesFilter) {
            elements.analysesFilter.addEventListener('change', filterAnalyses);
        }
        
        
        // Epicrisis tab buttons
        if (elements.copyEpicrisisBtn) {
            elements.copyEpicrisisBtn.addEventListener('click', copyEpicrisisMarkdown);
        }

        // Report tab buttons
        if (elements.copyReportBtn) {
            elements.copyReportBtn.addEventListener('click', copyReportMarkdown);
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
            elements.refreshScheduleBtn.addEventListener('click', () => fetchScheduleFromInputs(true));
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

        // Schedule modality chip buttons — update hidden select + re-fetch
        document.querySelectorAll('.schedule-mod-chips .chip').forEach(chip => {
            chip.addEventListener('click', () => {
                document.querySelectorAll('.schedule-mod-chips .chip').forEach(c => c.classList.remove('chip-active'));
                chip.classList.add('chip-active');
                const val = chip.dataset.labId || chip.dataset.lab || '';
                if (elements.scheduleLabFilter) {
                    elements.scheduleLabFilter.value = val;
                }
                fetchScheduleFromInputs();
            });
        });

        // Analyses modality chip buttons — update hidden select + filter
        document.querySelectorAll('.analyses-chips .chip').forEach(chip => {
            chip.addEventListener('click', () => {
                document.querySelectorAll('.analyses-chips .chip').forEach(c => c.classList.remove('chip-active'));
                chip.classList.add('chip-active');
                const val = chip.dataset.filter || chip.dataset.type || '';
                if (elements.analysesFilter) {
                    elements.analysesFilter.value = val;
                    elements.analysesFilter.dispatchEvent(new Event('change'));
                }
            });
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
            targetTab.style.display = 'block';
        }

        // Reflect the tab in the URL fragment (no scroll, no history entry)
        history.replaceState(null, '', `#${tabId}`);

        if (tabId === 'schedule' && !elements.scheduleTable?.dataset.loaded) {
            fetchScheduleFromInputs();
        }

        if (tabId === 'epicrisis') {
            loadEpicrisisLazily();
        }

        if (tabId === 'report') {
            loadReportLazily();
        }
    }

    let pendingEpicrisisData = null;
    let pendingReportData = null;

    async function loadReportLazily() {
        if (!pendingReportData || elements.patientReportMarkdown?.dataset.loaded) return;
        elements.patientReportMarkdown.dataset.loaded = '1';
        showLoading('Creating patient report…');
        try {
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
        showLoading('Loading discharge summaries…');
        try {
            await loadAndDisplayEpicrisis(pendingEpicrisisData);
            hideLoading();
        } catch (err) {
            console.error('Error loading epicrisis:', err);
            delete elements.epicrisisContent.dataset.loaded;
            showOverlayError('Failed to load discharge summaries');
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
        showLoading('Searching for patient…');
        hideError();

        try {
            setLoadingStep('Querying Hipocrate…');
            log('Starting patient search...');
            const searchResult = await performPatientSearch(cnp);
            log('Patient search result:', searchResult);

            if (!searchResult.success) {
                if (searchResult.needsSelection) {
                    hideLoading();
                    const chosen = await showPatientSelection(searchResult.candidates);
                    if (!chosen) return; // user dismissed
                    showLoading('Loading patient record…');
                    setLoadingStep('Fetching selected patient…');
                    const r = await fetch(`/fhir/Patient/${chosen.id}`);
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

            setLoadingStep('Fetching imaging studies…');
            log('Fetching analyses data for patient:', patientCode);
            const analysesResult = await fetchAnalysesData(patientCode);
            log('Analyses data result:', analysesResult);

            if (!analysesResult.success) {
                // Non-fatal — patient loads, analyses are unavailable
                const eyebrow = document.getElementById('analysesEyebrow');
                if (eyebrow) eyebrow.dataset.warning = analysesResult.message;
            }

            const analysesData = analysesResult.data || { resourceType: 'Bundle', entry: [] };
            log('Analyses data retrieved:', analysesData);

            setLoadingStep('Building patient profile…');
            log('Displaying patient data...');
            await displayPatientData(patientData, analysesData);

            setLoadingStep('Loading diagnostic reports…');
            log('Loading and displaying reports...');
            await loadAndDisplayReports(analysesData);

            // Epicrisis is lazy-loaded on first visit to its tab
            pendingEpicrisisData = patientData;
            if (elements.epicrisisContent) delete elements.epicrisisContent.dataset.loaded;

            // Report is lazy-loaded on first visit to its tab
            pendingReportData = { patientData, analysesData };
            if (elements.patientReportMarkdown) delete elements.patientReportMarkdown.dataset.loaded;

            log('Switching to patient tab...');
            switchToPatientTab();

            log('All data loading complete');
            hideLoading();

        } catch (err) {
            console.error('Error in handleFormSubmit:', err);
            showOverlayError('An unexpected error occurred. Please try again.');
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
            const searchResponse = await fetch(`/fhir/Patient?q=${encodeURIComponent(identifier)}`);
            
            if (!searchResponse.ok) {
                if (searchResponse.status === 401) {
                    return {
                        success: false,
                        message: 'Authentication required. Please refresh the page and enter your credentials.'
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
                    const r = await fetch(`/fhir/Patient/${patientCode}`);
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
            const overlay = document.createElement('div');
            overlay.className = 'modal-backdrop';
            overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:var(--z-overlay);display:flex;align-items:center;justify-content:center';

            const box = document.createElement('div');
            box.className = 'card';
            box.style.cssText = 'min-width:320px;max-width:480px;max-height:70vh;overflow-y:auto;padding:var(--spacing-lg)';
            box.setAttribute('role', 'dialog');
            box.setAttribute('aria-modal', 'true');
            box.setAttribute('aria-label', 'Select patient');

            const heading = document.createElement('h3');
            heading.textContent = `${candidates.length} patients found — select one:`;
            box.appendChild(heading);

            const dismiss = (result) => { document.body.removeChild(overlay); resolve(result); };

            candidates.forEach(patient => {
                const nameObj = Array.isArray(patient.name) ? patient.name[0] : patient.name;
                const name = nameObj?.text || [nameObj?.family, ...(nameObj?.given || [])].filter(Boolean).join(' ') || patient.id;
                const btn = document.createElement('button');
                btn.className = 'btn-secondary';
                btn.style.cssText = 'display:block;width:100%;margin-top:var(--spacing-sm);text-align:left';
                btn.textContent = name;
                btn.addEventListener('click', () => dismiss(patient));
                box.appendChild(btn);
            });

            const cancel = document.createElement('button');
            cancel.className = 'btn-secondary';
            cancel.style.cssText = 'display:block;width:100%;margin-top:var(--spacing-md)';
            cancel.textContent = 'Cancel';
            cancel.addEventListener('click', () => dismiss(null));
            box.appendChild(cancel);

            overlay.appendChild(box);
            document.body.appendChild(overlay);

            // Trap focus inside the dialog; close on Escape
            const focusable = () => [...box.querySelectorAll('button')];
            const trapFocus = e => {
                if (e.key === 'Escape') { dismiss(null); return; }
                if (e.key !== 'Tab') return;
                const els = focusable();
                const first = els[0], last = els[els.length - 1];
                if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
                    e.preventDefault();
                    (e.shiftKey ? last : first).focus();
                }
            };
            overlay.addEventListener('keydown', trapFocus);
            // Focus first button after paint
            requestAnimationFrame(() => focusable()[0]?.focus());
        });
    }

    async function fetchAnalysesData(patientCode) {
        try {
            
            const analysesResponse = await fetch(`/fhir/ServiceRequest?patient=${patientCode}`);
            
            if (!analysesResponse.ok) {
                if (analysesResponse.status === 401) {
                    return {
                        success: false,
                        message: 'Authentication required. Please refresh the page and enter your credentials.'
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
        ['analyses-tab', 'epicrisis-tab', 'report-tab'].forEach(id => {
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
        // Clear patient data with null checks
        if (elements.patientId) elements.patientId.textContent = '';
        if (elements.patientName) elements.patientName.textContent = '';
        if (elements.patientCnp) elements.patientCnp.textContent = '';
        if (elements.patientGender) elements.patientGender.innerHTML = '';
        if (elements.patientDiagnosis) { elements.patientDiagnosis.textContent = ''; elements.patientDiagnosis.hidden = true; }
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = '';
        if (elements.patientAvatar) elements.patientAvatar.className = 'fas fa-user-injured';
        if (elements.patientPhone) elements.patientPhone.textContent = '';
        if (elements.patientEmail) elements.patientEmail.textContent = '';
        if (elements.patientAddress) elements.patientAddress.textContent = '';
        if (elements.navPatientLabel) elements.navPatientLabel.textContent = 'Patient Profile';
        if (elements.historyList) elements.historyList.innerHTML = '';
        if (elements.historyEmpty) elements.historyEmpty.hidden = true;
        if (elements.presentationsCount) elements.presentationsCount.textContent = '0';
        if (elements.checkinsCount) elements.checkinsCount.textContent = '0';
        if (elements.checkoutsCount) elements.checkoutsCount.textContent = '0';
        
        // Clear analyses with null checks
        if (elements.analysesGrid) elements.analysesGrid.innerHTML = '';
        if (elements.noAnalyses) elements.noAnalyses.style.display = 'none';
        
        // Clear epicrisis
        pendingEpicrisisData = null;
        if (elements.epicrisisContent) {
            elements.epicrisisContent.innerHTML = '';
            delete elements.epicrisisContent.dataset.markdown;
            delete elements.epicrisisContent.dataset.loaded;
        }
        // Clear report tab
        pendingReportData = null;
        if (elements.patientReportMarkdown) {
            elements.patientReportMarkdown.innerHTML = '';
            delete elements.patientReportMarkdown.dataset.markdown;
            delete elements.patientReportMarkdown.dataset.loaded;
        }
        const reportCard = document.getElementById('reportCard');
        if (reportCard) reportCard.hidden = true;
        
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
    }

    let whoamiData = null;

    async function fetchWhoami() {
        if (whoamiData) return whoamiData;
        const resp = await fetch('/api/whoami');
        if (!resp.ok) throw new Error(`Whoami request failed (${resp.status})`);
        const data = await resp.json();
        if (data.status !== 'success' || !data.user) {
            throw new Error(data.message || 'User data not available');
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
        modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
        modal.addEventListener('cancel', () => modal.remove());

        modal.querySelector('.user-logout-btn').addEventListener('click', async () => {
            try {
                const resp = await fetch('/api/logout', { method: 'POST' });
                if (!resp.ok) throw new Error(`Logout failed (${resp.status})`);
                whoamiData = null;
                closeModal();
                showToast('Hipocrate session closed. Close the browser to clear saved credentials.', 'success');
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
        } catch (err) {
            nameEl.textContent = 'Unavailable';
            showToast(`Could not load user info: ${err.message}`, 'error');
        }
    }

    
    function filterAnalyses() {
        const searchTerm = elements.analysesSearch ? elements.analysesSearch.value.toLowerCase() : '';
        const filterType = elements.analysesFilter ? elements.analysesFilter.value : 'all';

        const cards = elements.analysesGrid.querySelectorAll('.analysis-card');
        let visible = 0;
        cards.forEach(card => {
            const type = card.dataset.type || '';
            const text = card.textContent.toLowerCase();
            const show = (searchTerm ? text.includes(searchTerm) : true) &&
                         (filterType === 'all' || type === filterType);
            card.style.display = show ? 'block' : 'none';
            if (show) visible++;
        });
        if (elements.noAnalyses) elements.noAnalyses.style.display = visible === 0 ? 'block' : 'none';
    }
    
    async function copyMarkdown(markdownEl, btn) {
        const markdown = markdownEl?.dataset.markdown;
        if (!markdown) {
            showToast('No content to copy', 'warning');
            return;
        }
        const flash = () => {
            const orig = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> <span>Copied!</span>';
            setTimeout(() => { btn.innerHTML = orig; }, 2000);
        };
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

    function copyEpicrisisMarkdown() { return copyMarkdown(elements.epicrisisContent, elements.copyEpicrisisBtn); }
    function copyReportMarkdown()    { return copyMarkdown(elements.patientReportMarkdown, elements.copyReportBtn); }
    
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
            'radio': { name: 'X-Ray',       icon: 'fa-x-ray'     },
            'ct':    { name: 'CT',          icon: 'fa-computer'  },
            'irm':   { name: 'MRI',         icon: 'fa-magnet'    },
            'eco':   { name: 'Ultrasound',  icon: 'fa-heartbeat' },
            'rads':  { name: 'Fluoroscopy', icon: 'fa-radiation' },
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
            const reportResponse = await fetch(endpoint);

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

        const reportCard = document.getElementById('reportCard');
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
            setText('reportPatientName', name);
            setText('reportPatientId',   pid);
            setText('reportCNP',         cnp);
            setText('reportDOB',         dob ? `${dob}${age ? ' (' + age + ')' : ''}` : '');
            setText('reportSex',         gender);

            // ── §2 + §4 Encounters (parallel with analyses) ──────────────
            const [analysesMarkdown, epicrisisMarkdown, encounters] = await Promise.all([
                analysesData ? populateAnalysesMarkdown(analysesData) : Promise.resolve(''),
                generateEpicrisisMarkdown(patientData),
                (async () => {
                    const checkoutIds = extractCheckoutIds(patientData);
                    const checkinIds  = extractCheckinIds(patientData);
                    const allIds = [...checkinIds, ...checkoutIds]; // active admissions first
                    if (!allIds.length) return [];
                    const enc = await limitedMap(allIds, MAX_CONCURRENT_REQUESTS,
                        async id => { try { return await fetchEncounterDataForCheckout(id); } catch { return null; } });
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

            // §2 Admission — active inpatient first, then most recent discharged with epicrisis
            const currentAdm = encounters.find(e => e.enc.status === 'in-progress')
                             || encounters.find(e => extractEpicrisisText(e.enc))
                             || encounters[0];
            const secAdmission = document.getElementById('reportSectionAdmission');
            if (currentAdm && secAdmission) {
                const enc = currentAdm.enc;
                const isActive = enc.status === 'in-progress';

                const titleEl = document.getElementById('reportAdmissionTitle');
                if (titleEl) {
                    const icon = titleEl.querySelector('i');
                    titleEl.textContent = isActive ? ' Current Admission' : ' Last Admission';
                    if (icon) titleEl.prepend(icon);
                }

                const start = enc.period?.start ? formatDate(enc.period.start) : '';
                const end   = enc.period?.end   ? formatDate(enc.period.end)   : '';
                const ms    = (enc.period?.start && enc.period?.end)
                    ? new Date(enc.period.end) - new Date(enc.period.start) : 0;
                const nights = ms > 0 ? Math.round(ms / 86400000) : 0;
                const periodEl = document.getElementById('reportAdmissionPeriod');
                if (periodEl) {
                    periodEl.textContent = isActive
                        ? `${start} → present (ongoing)`
                        : `${start} → ${end}${nights ? ` (${nights} ${nights === 1 ? 'night' : 'nights'})` : ''}`;
                }

                const textEl = document.getElementById('reportAdmissionText');
                if (textEl) {
                    if (isActive) {
                        // Inpatient — compose from checkin fields
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
                        textEl.textContent = parts.join('\n\n');
                    } else {
                        // Discharged — show full epicrisis
                        textEl.textContent = extractEpicrisisText(enc).trim();
                    }
                }
                secAdmission.hidden = false;
            }

            // §3 Recent imaging — up to 5 most recent entries from analysesData
            const secImaging = document.getElementById('reportSectionImaging');
            const imagingList = document.getElementById('reportImagingList');
            const MOD_SHORT = { radio: 'XR', ct: 'CT', irm: 'MR', eco: 'US', rads: 'FL' };
            const MOD_VAR   = { radio: '--mod-xr', ct: '--mod-ct', irm: '--mod-mr', eco: '--mod-us', rads: '--mod-fl' };
            if (imagingList && analysesData?.entry?.length) {
                const entries = [...analysesData.entry]
                    .filter(e => MOD_SHORT[e.resource?.code?.coding?.[0]?.code])
                    .sort((a, b) => (b.resource.authoredOn || '') > (a.resource.authoredOn || '') ? 1 : -1)
                    .slice(0, 5);

                const reports = await limitedMap(entries, MAX_CONCURRENT_REQUESTS, e => {
                    const sr = e.resource;
                    return getReportContent(sr.id, sr.code?.coding?.[0]?.code);
                });

                imagingList.innerHTML = '';
                entries.forEach((entry, idx) => {
                    const sr = entry.resource;
                    const mod  = sr.code?.coding?.[0]?.code || '';
                    const desc = sr.code?.coding?.[0]?.display || MODALITY_INFO[mod]?.label || mod;
                    const date = sr.authoredOn ? formatDate(sr.authoredOn) : '';
                    const code = sr.identifier?.[0]?.value || sr.id || '';
                    const isUrgent = sr.priority === 'urgent';
                    const physician = sr.performer?.[0]?.display || '';
                    const reportText = reports[idx] || '';

                    const row = document.createElement('div');
                    row.className = 'report-imaging-row';

                    const header = document.createElement('div');
                    header.className = 'report-imaging-header';

                    const badge = document.createElement('span');
                    badge.className = 'report-mod-badge';
                    badge.style.setProperty('--mod-color', `var(${MOD_VAR[mod] || '--accent'})`);
                    badge.textContent = MOD_SHORT[mod] || mod.toUpperCase();

                    const title = document.createElement('span');
                    title.className = 'report-imaging-title';
                    title.textContent = desc;

                    const meta = document.createElement('span');
                    meta.className = 'report-imaging-meta';
                    meta.textContent = [date, code ? '#' + code : ''].filter(Boolean).join(' · ');

                    header.append(badge, title, meta);

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
                        const sig = document.createElement('div');
                        sig.className = 'report-imaging-sig';
                        sig.innerHTML = `<i class="fas fa-signature"></i> ${physician}`;
                        row.appendChild(sig);
                    }

                    imagingList.appendChild(row);
                });
                if (secImaging) secImaging.hidden = false;
            }

            // §4 Hospitalisation timeline
            const secTimeline = document.getElementById('reportSectionTimeline');
            const timelineEl  = document.getElementById('reportTimeline');
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

            // Stash combined markdown for Copy button
            const patientMarkdown = await generatePatientMarkdown(patientData);
            const combined = patientMarkdown + epicrisisMarkdown + analysesMarkdown;
            if (markdownStore) markdownStore.dataset.markdown = combined;

            if (reportCard) reportCard.hidden = false;
            log('Patient report displayed successfully');

        } catch (error) {
            console.error('Error displaying patient report:', error);
        }
    }
    
    async function generatePatientMarkdown(patientData) {
        log('Generating patient report markdown');

        const name = formatPatientName(patientData.name);
        const age = calculateAge(patientData.birthDate);
        const gender = formatGender(patientData.gender);
        const dob = formatBirthDate(patientData.birthDate);
        const cnp = extractCNP(patientData.identifier) || 'N/A';
        const stats = extractMedicalStats(patientData);

        let markdown = `# PATIENT CLINICAL REPORT\n\n`;
        markdown += `## Patient\n\n`;
        markdown += `**Name:** ${name}  \n`;
        markdown += `**Age:** ${age} | **Sex:** ${gender} | **DOB:** ${dob}  \n`;
        markdown += `**CNP:** ${cnp}  \n\n`;

        markdown += `## Clinical History\n\n`;
        markdown += `- **Total presentations:** ${stats.encounters}\n`;
        markdown += `- **Admissions:** ${stats.admissions}\n`;
        markdown += `- **Discharges:** ${stats.discharges}\n\n`;

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
            const response = await fetch(`/fhir/Encounter/${checkoutId}`);
            
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
        elements.analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
        const titleEl = document.getElementById('loadingTitle');
        if (titleEl) titleEl.textContent = title;
        if (elements.loadingStep) elements.loadingStep.textContent = '';
    }

    function setLoadingStep(text) {
        if (elements.loadingStep) elements.loadingStep.textContent = text;
    }
    
    // Markdown to HTML conversion now uses marked.js library
    // marked.parse(markdownText) converts markdown to HTML

    function displayPatientData(patientData, analysesData) {
        log('Displaying patient data:', patientData);
        log('Analyses data:', analysesData);
        
        // Enhanced patient information display with better formatting
        displayPatientBasicInfo(patientData);
        
        // Extract and display medical statistics
        const stats = extractMedicalStats(patientData);
        log('Extracted medical stats:', stats);
        displayMedicalStats(stats);
        
        elements.analysesGrid.innerHTML = '';
        elements.noAnalyses.style.display = 'none';

        // Hospitalisation history loads lazily; don't block the profile render
        loadHospitalisationHistory(patientData);

        log('Patient data display completed');
    }

    async function loadHospitalisationHistory(patientData) {
        if (!elements.historyList) return;
        elements.historyList.innerHTML = '';
        if (elements.historyEmpty) elements.historyEmpty.hidden = true;

        const checkoutIds = extractCheckoutIds(patientData);
        if (checkoutIds.length === 0) {
            if (elements.historyEmpty) elements.historyEmpty.hidden = false;
            return;
        }

        if (elements.historyLoading) elements.historyLoading.hidden = false;
        try {
            const encounters = await limitedMap(
                checkoutIds,
                MAX_CONCURRENT_REQUESTS,
                async id => {
                    try { return await fetchEncounterDataForCheckout(id); }
                    catch (_) { return null; }
                }
            );

            const items = encounters
                .filter(Boolean)
                .map(enc => ({
                    enc,
                    start: enc.period?.start || '',
                    end: enc.period?.end || ''
                }))
                .sort((a, b) => (b.end || b.start).localeCompare(a.end || a.start));

            if (items.length === 0) {
                if (elements.historyEmpty) elements.historyEmpty.hidden = false;
                return;
            }

            // Populate diagnosis badge from most recent discharge if not already set
            if (elements.patientDiagnosis && elements.patientDiagnosis.hidden) {
                const latestDx = extractDiagnosisText(items[0].enc);
                if (latestDx) {
                    elements.patientDiagnosis.textContent = latestDx;
                    elements.patientDiagnosis.hidden = false;
                }
            }

            const tmpl = document.getElementById('history-item-template');
            items.forEach(({ enc, start, end }, idx) => {
                const li = tmpl.content.cloneNode(true).querySelector('.history-item');

                const period = [start && formatDate(start), end && formatDate(end)]
                    .filter(Boolean).join(' → ');
                li.querySelector('.history-period').textContent = period || 'Unknown period';

                // Nights badge
                const nightsEl = li.querySelector('.history-nights');
                if (nightsEl && start && end) {
                    const ms = new Date(end) - new Date(start);
                    const nights = Math.round(ms / 86400000);
                    if (nights > 0) nightsEl.textContent = `${nights}d`;
                    else nightsEl.hidden = true;
                } else if (nightsEl) nightsEl.hidden = true;

                li.querySelector('.history-diagnosis').textContent =
                    extractDiagnosisText(enc) || 'No diagnosis recorded';

                // Hide the connector line on the last item
                if (idx === items.length - 1) {
                    const line = li.querySelector('.history-line');
                    if (line) line.hidden = true;
                }

                li.querySelector('.history-load').addEventListener('click', () => switchTab('epicrisis'));
                elements.historyList.appendChild(li);
            });
        } catch (err) {
            log('Failed to load hospitalisation history:', err);
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
        if (elements.patientId) elements.patientId.textContent = patientData.id ? `ID: ${patientData.id}` : '';

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

        if (elements.patientAvatar) {
            const ageNum = ageLabel ? parseInt(ageLabel, 10) : null;
            const female = patientData.gender === 'female';
            let icon;
            if (ageNum === null)      icon = 'fa-user-injured';
            else if (ageNum <= 2)     icon = 'fa-baby';
            else if (ageNum <= 12)    icon = female ? 'fa-child-dress' : 'fa-child';
            else if (ageNum <= 64)    icon = female ? 'fa-person-dress' : 'fa-person';
            else                      icon = 'fa-person-cane';
            elements.patientAvatar.className = `fas ${icon}`;
        }
        log('Age set to:', age);
        
        // Personal info fields
        const cnp = extractCNP(patientData.identifier);
        if (elements.patientCnp)       elements.patientCnp.textContent       = cnp || '—';
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = formatBirthDate(patientData.birthDate) || '—';

        const contactInfo = extractContactInfo(patientData.telecom);
        if (elements.patientPhone) elements.patientPhone.textContent = contactInfo.phone || '—';
        if (elements.patientEmail) elements.patientEmail.textContent = contactInfo.email || '—';
        if (elements.patientAddress) elements.patientAddress.textContent = patientData.address?.[0]?.text || '—';
        log('CNP:', cnp, 'Phone:', contactInfo.phone, 'Email:', contactInfo.email);
    }
    
    // Enhanced name formatting
    function toTitleCase(str) {
        return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
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
        if (elements.reportsCount) {
            elements.reportsCount.textContent = '0'; // Will be updated when reports load
            log('Reports count updated');
        }
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
            const studyResponse = await fetch(`/fhir/ImagingStudy/${studyId}`);
            
            if (!studyResponse.ok) {
                const msg = studyResponse.status === 401
                    ? 'Authentication required. Please refresh the page.'
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
        if (studyData.note?.length > 0)
            addStudyInfoRow(studyInfo, 'fa-sticky-note', 'Note', studyData.note[0].text || 'N/A');
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
    
    // Function to load and display reports progressively
    async function loadAndDisplayReports(analysesData) {
        const includedTypes = ['radio', 'ct', 'irm', 'eco', 'rads'];

        if (!(analysesData.resourceType === 'Bundle' && analysesData.entry?.length > 0)) {
            elements.noAnalyses.style.display = 'block';
            elements.analysesGrid.innerHTML = '';
            return;
        }

        const filteredEntries = analysesData.entry.filter(e =>
            includedTypes.includes(e.resource?.code?.coding?.[0]?.code)
        );

        if (filteredEntries.length === 0) {
            elements.noAnalyses.style.display = 'block';
            elements.analysesGrid.innerHTML = '';
            return;
        }

        elements.noAnalyses.style.display = 'none';
        if (elements.reportsCount) elements.reportsCount.textContent = filteredEntries.length;
        elements.analysesGrid.innerHTML = '';

        // Update analyses header eyebrow + meta + chip counts
        const eyebrow = document.getElementById('analysesEyebrow');
        const metaEl = document.getElementById('analysesMeta');
        const patientNameEl = elements.patientName;
        if (eyebrow && patientNameEl?.textContent) {
            eyebrow.textContent = `Analyses · ${patientNameEl.textContent}`;
        }
        const countByType = {};
        for (const e of filteredEntries) {
            const t = e.resource?.code?.coding?.[0]?.code || 'unknown';
            countByType[t] = (countByType[t] || 0) + 1;
        }
        if (metaEl) {
            const parts = includedTypes.filter(t => countByType[t]).map(t => `${countByType[t]} ${MODALITY_INFO[t]?.label || t}`);
            metaEl.textContent = `${filteredEntries.length} imaging ${filteredEntries.length === 1 ? 'study' : 'studies'}${parts.length ? ' · ' + parts.join(', ') : ''}`;
        }
        document.querySelectorAll('.analyses-chips .chip').forEach(chip => {
            const f = chip.dataset.filter;
            const count = f === 'all' ? filteredEntries.length : (countByType[f] || 0);
            const label = chip.textContent.replace(/\s*\(\d+\)$/, '');
            chip.textContent = `${label} (${count})`;
            if (f !== 'all' && count === 0) { chip.style.opacity = '0.4'; chip.disabled = true; }
            else { chip.style.opacity = ''; chip.disabled = false; }
        });

        // Create all cards immediately (request metadata is already available)
        const cards = filteredEntries.map(entry => {
            const sr = entry.resource;
            const type = sr.code?.coding?.[0]?.code || 'unknown';
            const text = sr.code?.coding?.[0]?.display || 'analysis';
            const card = createAnalysisCard(sr, type, text);
            elements.analysesGrid.appendChild(card);
            return card;
        });

        // Lazily fetch report for each card as it scrolls into view
        const observer = new IntersectionObserver((entries, obs) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    obs.unobserve(entry.target);
                    fetchAndFillReport(entry.target);
                }
            }
        }, { rootMargin: '120px' });

        for (const card of cards) observer.observe(card);
    }
    
    const MODALITY_INFO = {
        radio:  { icon: 'fa-x-ray',      label: 'X-Ray' },
        ct:     { icon: 'fa-computer',   label: 'CT' },
        irm:    { icon: 'fa-magnet',     label: 'MRI' },
        eco:    { icon: 'fa-heartbeat',  label: 'Ultrasound' },
        rads:   { icon: 'fa-radiation',  label: 'Fluoroscopy' },
        fluoro: { icon: 'fa-radiation',  label: 'Fluoroscopy' },
        lab:    { icon: 'fa-flask',      label: 'Laboratory' },
    };

    const MODALITY_AVATAR = {
        radio:  { abbr: 'XR',  cls: 'mod-xr' },
        ct:     { abbr: 'CT',  cls: 'mod-ct' },
        irm:    { abbr: 'MR',  cls: 'mod-mr' },
        eco:    { abbr: 'US',  cls: 'mod-us' },
        fluoro: { abbr: 'FL',  cls: 'mod-fl' },
        rads:   { abbr: 'FL',  cls: 'mod-fl' },
        lab:    { abbr: 'LB',  cls: 'mod-lab' },
    };

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
        const iconEl = article.querySelector('.modality-icon');
        if (iconEl) iconEl.className = `modality-icon fas ${modality.icon}`;

        // Modality circle avatar (editorial redesign)
        const circleEl = article.querySelector('.mod-circle');
        if (circleEl) {
            const circleAvatar = MODALITY_AVATAR[analysisType] || { abbr: '?', cls: '' };
            circleEl.textContent = circleAvatar.abbr;
            if (circleAvatar.cls) circleEl.classList.add(circleAvatar.cls);
        }

        const typeText = article.querySelector('.type-text');
        if (typeText) typeText.textContent = analysisText || modality.label;

        const reportId = article.querySelector('.report-id');
        if (reportId) reportId.textContent = `#${serviceRequest.id}`;

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

        return article;
    }

    function setCardIndication(article, text) {
        if (!text) return;
        const indEl   = article.querySelector('.card-indication');
        const indText = article.querySelector('.card-indication-text');
        if (indText) indText.textContent = text;
        if (indEl) indEl.hidden = false;
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

        try {
            const resp = await fetch(endpoint);
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
                if (!existing?.textContent) {
                    setCardIndication(article, indicationNotes[0].text);
                }
            }

            // Report text
            const forms = data.presentedForm || [];
            const hasReport = forms.length > 0
                || resultNotes.some(n => n.text)
                || Boolean(data.conclusion);

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

            const reportPreview = article.querySelector('.report-preview');
            if (reportPreview) {
                const notes = resultNotes;
                if (forms.length > 0) {
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
                } else if (notes.length > 0) {
                    const series = data.series || [];
                    const showTitles = notes.length > 1 && series.length >= notes.length;
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
                } else if (data.conclusion) {
                    const div = document.createElement('div');
                    div.innerHTML = marked.parse(data.conclusion);
                    reportPreview.appendChild(div);
                } else {
                    article.classList.add('no-report');
                }
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
        }
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

    function extractEpicrisisText(encounterData) {
        if (!encounterData.note || !Array.isArray(encounterData.note)) return '';
        return encounterData.note.map(note => note.text || '').join('\n\n');
    }

    async function loadAndDisplayEpicrisis(patientData) {
        const checkoutIds = extractCheckoutIds(patientData);
        if (checkoutIds.length === 0) return;

        const encounters = await limitedMap(
            checkoutIds,
            MAX_CONCURRENT_REQUESTS,
            async id => {
                try { return await fetchEncounterDataForCheckout(id); }
                catch { return null; }
            }
        );

        // Keep only encounters that have an epicrisis, sorted most-recent-discharge first
        const valid = encounters
            .map((enc, i) => enc && extractEpicrisisText(enc) ? { enc, checkoutId: checkoutIds[i] } : null)
            .filter(Boolean)
            .sort((a, b) => {
                const da = a.enc.period?.end || '';
                const db = b.enc.period?.end || '';
                return db > da ? 1 : -1;
            });

        if (valid.length === 0) return;

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
            const epicrisisText = extractEpicrisisText(enc);
            const icd = extractDiagnosisText(enc) || '';
            const admission = enc.period?.start ? formatDate(enc.period.start) : '';
            const discharge = enc.period?.end ? formatDate(enc.period.end) : '';
            const service = enc.serviceType?.display || '';
            const ward = enc.location?.slice(-1)[0]?.location?.display || '';
            const attender = enc.participant?.find(p =>
                p.type?.some(t => t.coding?.some(c => c.code === 'ATND'))
            )?.individual?.display || '';

            // Night count
            let nights = '';
            if (admission && discharge) {
                const ms = new Date(discharge) - new Date(admission);
                const n = Math.round(ms / 86400000);
                nights = `${n} ${n === 1 ? 'night' : 'nights'}`;
            }

            // Markdown
            const meta = [];
            if (admission) meta.push(`**Admission:** ${admission}`);
            if (discharge) meta.push(`**Discharge:** ${discharge}`);
            if (ward)      meta.push(`**Ward:** ${ward}`);
            if (attender)  meta.push(`**Attending:** ${attender}`);
            if (service)   meta.push(`**Service:** ${service}`);
            markdown += valid.length === 1 ? `# ${icd}\n\n` : `## ${index + 1}. ${icd}\n\n`;
            if (meta.length) markdown += `${meta.join(' · ')}  \n\n`;
            markdown += epicrisisText.trim() + '\n\n';
            if (index < valid.length - 1) markdown += '---\n\n';

            // Accordion card
            const isOpen = index === 0;
            const card = document.createElement('div');
            card.className = 'epi-card' + (isOpen ? ' epi-card-open' : '');
            card.id = `epicrisis-${item.checkoutId}`;
            card.dataset.markdown = `# ${icd}\n\n`
                + (meta.length ? `${meta.join(' · ')}  \n\n` : '')
                + epicrisisText.trim() + '\n';

            // Toggle button (header)
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'epi-card-btn';
            btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

            // Left: dot + date range + service label
            const btnLeft = document.createElement('div');
            btnLeft.className = 'epi-btn-left';

            const dot = document.createElement('div');
            dot.className = 'epi-dot';

            const dateBlock = document.createElement('div');
            const dateRow = document.createElement('div');
            dateRow.className = 'epi-date-range';
            dateRow.textContent = `${admission} → ${discharge}`;
            const serviceRow = document.createElement('div');
            serviceRow.className = 'epi-service';
            const serviceParts = [ward, attender].filter(Boolean);
            serviceRow.textContent = serviceParts.length ? serviceParts.join(' · ') : (service || 'Admission');
            dateBlock.append(dateRow, serviceRow);
            btnLeft.append(dot, dateBlock);

            // Right: ICD badge + nights + chevron
            const btnRight = document.createElement('div');
            btnRight.className = 'epi-btn-right';

            if (icd) {
                const icdBadge = document.createElement('span');
                icdBadge.className = 'epi-icd-badge';
                icdBadge.textContent = icd;
                btnRight.appendChild(icdBadge);
            }
            if (nights) {
                const nightsSpan = document.createElement('span');
                nightsSpan.className = 'epi-nights';
                nightsSpan.textContent = nights;
                btnRight.appendChild(nightsSpan);
            }
            const chevron = document.createElement('i');
            chevron.className = `fas fa-chevron-${isOpen ? 'up' : 'down'} epi-chevron`;
            btnRight.appendChild(chevron);

            btn.append(btnLeft, btnRight);

            // Body
            const body = document.createElement('div');
            body.className = 'epi-card-body';
            body.hidden = !isOpen;
            const inner = document.createElement('div');
            inner.className = 'epi-card-inner';
            const prose = document.createElement('div');
            prose.className = 'epi-prose';
            prose.innerHTML = marked.parse(epicrisisText.trim());
            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'btn-secondary epi-copy-btn';
            copyBtn.setAttribute('aria-label', 'Copy this epicrisis as Markdown');
            copyBtn.innerHTML = '<i class="fas fa-copy"></i> <span>Copy</span>';
            copyBtn.addEventListener('click', () => copyMarkdown(card, copyBtn));
            inner.append(prose, copyBtn);
            body.appendChild(inner);

            // Toggle logic
            btn.addEventListener('click', () => {
                const open = card.classList.toggle('epi-card-open');
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
                body.hidden = !open;
                chevron.className = `fas fa-chevron-${open ? 'up' : 'down'} epi-chevron`;
            });

            card.append(btn, body);
            elements.epicrisisContent.appendChild(card);
        });

        if (metaEl) {
            const icdSample = valid[0] ? (extractDiagnosisText(valid[0].enc) || '') : '';
            metaEl.textContent = `${valid.length} ${valid.length === 1 ? 'admission' : 'admissions'}${icdSample ? ' · ' + icdSample : ''}`;
        }

        elements.epicrisisContent.dataset.markdown = markdown;
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

    // Modality slug (category[0].coding[0].code) → compact chip; fluoro shares
    // the rads colour class used by the analysis cards
    const SCHEDULE_MODALITY_CHIP = {
        radio:  { label: 'X-Ray',  cls: 'radio' },
        ct:     { label: 'CT',     cls: 'ct' },
        irm:    { label: 'MRI',    cls: 'irm' },
        eco:    { label: 'Ultrasound',   cls: 'eco' },
        fluoro: { label: 'Fluoroscopy', cls: 'rads' },
        lab:    { label: 'Lab',    cls: 'lab' },
    };

    let scheduleEntries = [];

    async function showRequestModal(requestId, requestCode, patientName, modality, triggerEl, requesterName) {
        const tmpl = document.getElementById('schedule-request-modal-template');
        if (!tmpl) return;
        const modal = tmpl.content.cloneNode(true).querySelector('dialog');

        // Populate identity header immediately from data we already have
        const circleEl = modal.querySelector('.modal-mod-circle');
        const circleAvatar = MODALITY_AVATAR[modality] || { abbr: '?', cls: '' };
        circleEl.textContent = circleAvatar.abbr;
        if (circleAvatar.cls) circleEl.classList.add(circleAvatar.cls);

        modal.querySelector('.modal-type-name').textContent =
            MODALITY_INFO[modality]?.label || 'Report';
        modal.querySelector('.modal-request-code').textContent = requestCode;
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
        modal.addEventListener('click', e => { if (e.target === modal) modal.close(); });
        modal.addEventListener('close', () => document.body.removeChild(modal));
        modal.querySelector('.modal-load-patient-btn').addEventListener('click', () => {
            modal.close();
            loadPatientFromRequest(requestId, patientName, triggerEl);
        });

        bodyDiv.classList.add('report-empty');
        bodyDiv.textContent = 'Loading…';
        document.body.appendChild(modal);
        modal.showModal();

        try {
            const imagingTypes = ['radio', 'ct', 'irm', 'eco', 'rads', 'fluoro'];
            const isImaging = imagingTypes.includes(modality);
            const endpoint = isImaging
                ? `/fhir/ImagingStudy/${requestId}`
                : `/fhir/DiagnosticReport/${requestId}`;

            const repResp = await fetch(endpoint);
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

                // Examiner (reporting physician) appended below content
                const examiner = reportData.performer?.[0]?.actor?.display
                    || reportData.resultsInterpreter?.[0]?.display;

                renderReportContent(reportData, isImaging);

                if (examiner) {
                    const signed = document.createElement('p');
                    signed.className = 'report-modal-signed';
                    signed.innerHTML = `<i class="fas fa-signature" aria-hidden="true"></i> ${examiner}`;
                    bodyDiv.appendChild(signed);
                }
            } else if (repResp.status === 404) {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = 'Report not yet available.';
            } else {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = `Could not load report (HTTP ${repResp.status}).`;
            }
        } catch (err) {
            bodyDiv.classList.add('report-empty');
            bodyDiv.textContent = err.message;
        } finally {
            triggerEl.textContent = originalText;
            triggerEl.disabled = false;
        }

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
            const resp = await fetch(`/api/request/${requestId}/patient`);
            if (resp.ok) {
                const json = await resp.json();
                const patientId = json['patient.id'] || json.patient?.id;
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
        if (elements.scheduleLoading) elements.scheduleLoading.hidden = false;
        if (elements.noSchedule) elements.noSchedule.style.display = 'none';
        try {
            const resp = await fetch(url);
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
            if (elements.scheduleLoading) elements.scheduleLoading.hidden = true;
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

        if (elements.scheduleCount) {
            elements.scheduleCount.textContent = String(scheduleEntries.length);
            elements.scheduleCount.hidden = false;
        }

        if (scheduleEntries.length === 0) {
            if (elements.scheduleTable) elements.scheduleTable.hidden = true;
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

        scheduleEntries.forEach((r, idx) => {
            const authoredOn = r.authoredOn || '';
            const hasTime = authoredOn.includes(' ');
            const day = hasTime ? authoredOn.split(' ')[0] : authoredOn;
            const time = hasTime ? authoredOn.split(' ')[1] : '';

            const patientName = r.subject?.display || '';
            const requestCode = r.identifier?.[0]?.value || r.id || '';
            const section = r.note?.[0]?.text || '';
            const requestedBy = r.requester?.display || '';
            const laboratory = r.code?.text || '';
            const modalitySlug = r.category?.[0]?.coding?.[0]?.code || '';
            const status = r.status || '';
            const statusClass = SCHEDULE_STATUS_CLASS[status] || '';
            const isUrgent = r.priority === 'urgent';
            const avatar = MODALITY_AVATAR[modalitySlug] || { abbr: '?', cls: '' };
            const isLast = idx === scheduleEntries.length - 1;

            // Day group heading
            if (isMultiDay && day && day !== currentDay) {
                currentDay = day;
                const heading = document.createElement('p');
                heading.className = 'timeline-day-heading';
                heading.textContent = formatDayHeading(day);
                container.appendChild(heading);
            }

            // Row: time col + card
            const row = document.createElement('div');
            row.className = 'timeline-row';
            if (modalitySlug) row.dataset.modality = modalitySlug;

            // ── Time column ──
            const timeCol = document.createElement('div');
            timeCol.className = 'timeline-time-col';

            const timeEl = document.createElement('time');
            timeEl.className = 'timeline-time';
            timeEl.dateTime = authoredOn.replace(' ', 'T');
            timeEl.textContent = isMultiDay ? (time || day) : (time || authoredOn);
            timeCol.appendChild(timeEl);

            const dot = document.createElement('span');
            dot.className = `timeline-dot ${avatar.cls}`;
            timeCol.appendChild(dot);

            if (!isLast) {
                const line = document.createElement('span');
                line.className = 'timeline-line';
                timeCol.appendChild(line);
            }
            row.appendChild(timeCol);

            // ── Card ──
            const card = document.createElement('div');
            card.className = `timeline-card${isUrgent ? ' urgent-ring' : ''}`;

            // Modality avatar circle
            const avatarEl = document.createElement('div');
            avatarEl.className = `timeline-mod-avatar ${avatar.cls}`;
            avatarEl.textContent = avatar.abbr;
            avatarEl.title = MODALITY_INFO[modalitySlug]?.label || laboratory || modalitySlug;
            card.appendChild(avatarEl);

            // Card body
            const body = document.createElement('div');
            body.className = 'timeline-card-body';

            const patientRow = document.createElement('div');
            patientRow.className = 'timeline-patient-row';

            const nameBtn = document.createElement('button');
            nameBtn.className = 'timeline-card-patient';
            nameBtn.textContent = patientName;
            nameBtn.title = `Load patient record for ${patientName}`;
            nameBtn.addEventListener('click', () => loadPatientFromRequest(r.id, patientName, nameBtn));
            patientRow.appendChild(nameBtn);

            if (isUrgent) {
                const urgBadge = document.createElement('strong');
                urgBadge.className = 'urgent-badge';
                urgBadge.textContent = 'Urgent';
                patientRow.appendChild(urgBadge);
            }
            body.appendChild(patientRow);

            // Line 2: exam names (lazy-loaded) · modality
            const regionLine = document.createElement('div');
            regionLine.className = 'timeline-card-region';
            regionLine.textContent = laboratory;  // placeholder until exams load
            regionLine.dataset.requestId = r.id;
            body.appendChild(regionLine);

            // Line 3: department · physician · code
            const metaLine = document.createElement('div');
            metaLine.className = 'timeline-card-meta';

            const metaParts = [];
            if (section) {
                const sp = document.createElement('span');
                sp.innerHTML = `<i class="fas fa-hospital" aria-hidden="true"></i> `;
                sp.appendChild(document.createTextNode(section));
                metaParts.push(sp);
            }
            if (requestedBy) {
                const rp = document.createElement('span');
                rp.innerHTML = `<i class="fas fa-user-doctor" aria-hidden="true"></i> `;
                rp.appendChild(document.createTextNode(requestedBy));
                metaParts.push(rp);
            }

            const codeBtn = document.createElement('button');
            codeBtn.className = 'timeline-code';
            codeBtn.textContent = requestCode;
            codeBtn.title = `View request details (${requestCode})`;
            codeBtn.addEventListener('click', () => showRequestModal(r.id, requestCode, patientName, modalitySlug, codeBtn, requestedBy));

            metaParts.forEach((part, i) => {
                metaLine.appendChild(part);
                const sep = document.createElement('span');
                sep.textContent = '·';
                sep.setAttribute('aria-hidden', 'true');
                metaLine.appendChild(sep);
            });
            metaLine.appendChild(codeBtn);
            body.appendChild(metaLine);

            card.appendChild(body);

            // Status badge (right side)
            const statusBadge = document.createElement('span');
            statusBadge.className = `timeline-status-badge ${statusClass}`;
            statusBadge.textContent = SCHEDULE_STATUS_LABEL[status] || status;
            statusBadge.title = status;
            card.appendChild(statusBadge);

            row.appendChild(card);
            container.appendChild(row);
            scheduleExamObserver.observe(regionLine);
        });

        if (elements.scheduleTable) elements.scheduleTable.hidden = false;
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
            fetch(`/api/request/${id}/patient`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    const exams = data?.exams || [];
                    _examCache[id] = exams;
                    _applyExamLabel(el, exams);
                })
                .catch(() => {});
        });
    }, { rootMargin: '200px' });

    function _applyExamLabel(el, exams) {
        if (!exams.length) return;
        const modality = el.textContent;  // was set to laboratory as placeholder
        el.textContent = exams.join(', ') + (modality ? ' · ' + modality : '');
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
            { label: 'Exams',     value: total,     color: 'var(--ink, #0f172a)' },
            { label: 'Urgent',    value: urgent,    color: 'var(--urgent, #dc2626)' },
            { label: 'In lab',    value: inLab,     color: 'var(--st-inlab, #1d4ed8)' },
            { label: 'Completed', value: completed, color: 'var(--st-completed, #065f46)' },
        ];

        const sub = document.getElementById('scheduleHeroSub');
        if (sub) sub.textContent = `${total} exam${total !== 1 ? 's' : ''} in queue · most recent first`;

        elements.scheduleDayMetrics.innerHTML = '';
        metricDefs.forEach(m => {
            const div = document.createElement('div');
            div.className = 'schedule-metric';
            const val = document.createElement('span');
            val.className = 'schedule-metric-value';
            val.textContent = m.value;
            val.style.color = m.color;
            const lbl = document.createElement('span');
            lbl.className = 'schedule-metric-label';
            lbl.textContent = m.label;
            div.append(val, lbl);
            elements.scheduleDayMetrics.appendChild(div);
        });

        // Modality bars
        if (elements.scheduleModBars && total > 0) {
            const modalityCounts = {};
            scheduleEntries.forEach(r => {
                const slug = r.category?.[0]?.coding?.[0]?.code || 'other';
                modalityCounts[slug] = (modalityCounts[slug] || 0) + 1;
            });

            const modLabels = { radio: 'X-Ray', ct: 'CT', irm: 'MRI', eco: 'Ultrasound', fluoro: 'Fluoroscopy', lab: 'Laboratory' };
            const modColors = { radio: 'var(--mod-xr)', ct: 'var(--mod-ct)', irm: 'var(--mod-mr)', eco: 'var(--mod-us)', fluoro: 'var(--mod-fl)', lab: 'var(--mod-lab)' };

            elements.scheduleModBars.innerHTML = '';
            Object.entries(modalityCounts).sort((a, b) => b[1] - a[1]).forEach(([slug, count]) => {
                const bar = document.createElement('div');
                bar.className = 'schedule-mod-bar';
                const pct = Math.round(count / total * 100);
                const color = modColors[slug] || 'var(--muted)';
                bar.innerHTML = `<div class="schedule-mod-bar-header">
                    <span class="schedule-mod-bar-name">${modLabels[slug] || slug}</span>
                    <span class="schedule-mod-bar-count" style="color:${color}">${count}</span>
                </div>
                <div class="schedule-mod-bar-track">
                    <div class="schedule-mod-bar-fill" style="width:${pct}%;background:${color}"></div>
                </div>`;
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
