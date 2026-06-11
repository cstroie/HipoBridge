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
        patientAge: document.getElementById('patientAge'),
        patientGender: document.getElementById('patientGender'),
        patientBirthDate: document.getElementById('patientBirthDate'),
        patientPhone: document.getElementById('patientPhone'),
        patientEmail: document.getElementById('patientEmail'),
        presentationsCount: document.getElementById('presentationsCount'),
        checkinsCount: document.getElementById('checkinsCount'),
        checkoutsCount: document.getElementById('checkoutsCount'),
        reportsCount: document.getElementById('reportsCount'),
        // Analyses tab elements
        analysesGrid: document.getElementById('analysesGrid'),
        noAnalyses: document.getElementById('noAnalyses'),
        // Epicrisis tab elements
        epicrisisContent: document.getElementById('epicrisisContent'),
        copyEpicrisisBtn: document.getElementById('copyEpicrisisBtn'),
        // Report tab elements
        patientReportMarkdown: document.getElementById('patientReportMarkdown'),
        copyReportBtn: document.getElementById('copyReportBtn'),
        // Header elements
        quickSearch: document.getElementById('quickSearch'),
        quickSearchBtn: document.getElementById('quickSearchBtn'),
        themeToggle: document.getElementById('themeToggle'),
        // Search examples
        exampleBtns: document.querySelectorAll('.example-btn'),
        // Patient actions
        // Analyses actions
        analysesSearch: document.getElementById('analysesSearch'),
        analysesFilter: document.getElementById('analysesFilter'),
        // Epicrisis actions
        // Loading overlay
        loadingOverlay: document.getElementById('loadingOverlay'),
        loadingStep: document.getElementById('loadingStep'),
        // Recent searches
        recentSearchesList: document.getElementById('recentSearchesList'),
        // Schedule tab elements
        scheduleStartDate: document.getElementById('scheduleStartDate'),
        scheduleEndDate: document.getElementById('scheduleEndDate'),
        refreshScheduleBtn: document.getElementById('refreshScheduleBtn'),
        schedulePatientFilter: document.getElementById('schedulePatientFilter'),
        scheduleLabFilter:     document.getElementById('scheduleLabFilter'),
        scheduleSectionFilter: document.getElementById('scheduleSectionFilter'),
        scheduleTable: document.getElementById('scheduleTable'),
        scheduleBody: document.getElementById('scheduleBody'),
        noSchedule: document.getElementById('noSchedule')
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
        switchTab('schedule');
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
        
        
        // Example buttons
        elements.exampleBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const example = this.getAttribute('data-example');
                elements.cnpInput.value = example;
                showToast(`Using example: ${example}`, 'info');
            });
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
            elements.scheduleSectionFilter.addEventListener('change', fetchScheduleFromInputs);
        }
    }
    
    function switchTab(tabId) {
        // Update active nav item and aria-current
        elements.navItems.forEach(nav => {
            nav.classList.remove('active');
            nav.removeAttribute('aria-current');
        });
        const activeNavItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
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

        if (tabId === 'schedule' && !elements.scheduleTable?.dataset.loaded) {
            fetchScheduleFromInputs();
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
        showLoading();
        hideError();
        
        
        try {
            setLoadingStep('Searching Hipocrate for patient record...');
            log('Starting patient search...');
            const searchResult = await performPatientSearch(cnp);
            log('Patient search result:', searchResult);

            if (!searchResult.success) {
                if (searchResult.needsSelection) {
                    hideLoading();
                    const chosen = await showPatientSelection(searchResult.candidates);
                    if (!chosen) return; // user dismissed
                    showLoading();
                    setLoadingStep('Fetching selected patient record...');
                    const r = await fetch(`/fhir/Patient/${chosen.id}`);
                    searchResult.patientData = r.ok ? await r.json() : chosen;
                    searchResult.patientCode = chosen.id;
                    addToRecentSearches(cnp, searchResult.patientData);
                } else {
                    showToast(searchResult.message, 'error');
                    return;
                }
            }

            const { patientData, patientCode } = searchResult;
            if (!patientCode) {
                showToast('Could not determine patient ID. Please try again.', 'error');
                return;
            }
            log('Patient data retrieved:', patientData);
            log('Patient code:', patientCode);

            setLoadingStep('Fetching imaging studies and service requests...');
            log('Fetching analyses data for patient:', patientCode);
            const analysesResult = await fetchAnalysesData(patientCode);
            log('Analyses data result:', analysesResult);

            if (!analysesResult.success) {
                showToast(analysesResult.message + ' Showing patient data only.', 'warning');
            }

            const analysesData = analysesResult.data || { resourceType: 'Bundle', entry: [] };
            log('Analyses data retrieved:', analysesData);

            setLoadingStep('Building patient profile...');
            log('Displaying patient data...');
            await displayPatientData(patientData, analysesData);

            setLoadingStep('Loading diagnostic reports...');
            log('Loading and displaying reports...');
            await loadAndDisplayReports(analysesData);

            setLoadingStep('Loading discharge summaries...');
            log('Loading and displaying epicrisis...');
            await loadAndDisplayEpicrisis(patientData);

            setLoadingStep('Assembling full clinical report...');
            log('Loading and displaying report...');
            await loadAndDisplayReport(patientData, analysesData);

            log('Switching to patient tab...');
            switchToPatientTab();

            showToast('Patient data loaded', 'success');
            log('All data loading complete');
            
        } catch (err) {
            console.error('Error in handleFormSubmit:', err);
            showToast('An unexpected error occurred. Please try again.', 'error');
        } finally {
            hideLoading();
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
            box.style.cssText = 'min-width:320px;max-width:480px;max-height:70vh;overflow-y:auto;padding:var(--space-4)';
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
                btn.style.cssText = 'display:block;width:100%;margin-top:var(--space-2);text-align:left';
                btn.textContent = name;
                btn.addEventListener('click', () => dismiss(patient));
                box.appendChild(btn);
            });

            const cancel = document.createElement('button');
            cancel.className = 'btn-secondary';
            cancel.style.cssText = 'display:block;width:100%;margin-top:var(--space-3)';
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
        // Unhide nav items hidden by clearResults
        ['patient', 'analyses', 'epicrisis', 'report'].forEach(tabName => {
            const navEl = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
            if (navEl) navEl.style.display = 'block';
        });
        // Unhide sibling tab content panels (clearResults set hidden=true)
        ['analyses-tab', 'epicrisis-tab', 'report-tab'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.hidden = false;
        });
        switchTab('patient');
    }
    
    function hideLoading() {
        elements.loadingOverlay.style.display = 'none';
        elements.analyzeBtn.disabled = false;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }
    
    function clearResults() {
        // Clear patient data with null checks
        if (elements.patientId) elements.patientId.textContent = '';
        if (elements.patientName) {
            const nameSpan = elements.patientName.querySelector('#patient-tab-heading');
            if (nameSpan) nameSpan.textContent = '';
        }
        if (elements.patientCnp) elements.patientCnp.textContent = '';
        if (elements.patientGender) elements.patientGender.textContent = '';
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = '';
        if (elements.patientAvatar) elements.patientAvatar.className = 'fas fa-user-injured';
        if (elements.patientPhone) elements.patientPhone.textContent = '';
        if (elements.patientEmail) elements.patientEmail.textContent = '';
        if (elements.presentationsCount) elements.presentationsCount.textContent = '0';
        if (elements.checkinsCount) elements.checkinsCount.textContent = '0';
        if (elements.checkoutsCount) elements.checkoutsCount.textContent = '0';
        
        // Clear analyses with null checks
        if (elements.analysesGrid) elements.analysesGrid.innerHTML = '';
        if (elements.noAnalyses) elements.noAnalyses.style.display = 'none';
        
        // Clear epicrisis
        if (elements.epicrisisContent) {
            elements.epicrisisContent.innerHTML = '';
            delete elements.epicrisisContent.dataset.markdown;
        }
        
        // Clear report tab
        if (elements.patientReportMarkdown) elements.patientReportMarkdown.innerHTML = '';
        
        // Hide navigation tabs for patient data (keep always-visible tabs)
        elements.navItems.forEach(item => {
            const tab = item.getAttribute('data-tab');
            if (tab !== 'search' && tab !== 'schedule') {
                item.style.display = 'none';
            }
        });
        
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
            'radio': { name: 'X-Ray',        icon: 'fa-x-ray',    color: '#36a2eb' },
            'ct':    { name: 'CT Scan',      icon: 'fa-computer', color: '#ff6384' },
            'irm':   { name: 'MRI',          icon: 'fa-magnet',   color: '#ffce56' },
            'eco':   { name: 'Ultrasound',   icon: 'fa-heartbeat',color: '#4bc0c0' },
            'rads':  { name: 'Fluoroscopy',  icon: 'fa-radiation',color: '#9966ff' }
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
        
        const markdownContainer = elements.patientReportMarkdown;
        markdownContainer.replaceChildren((() => {
            const wrap = document.createElement('div');
            wrap.className = 'loading-content';
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin';
            const msg = document.createElement('p');
            msg.textContent = 'Assembling report…';
            wrap.append(icon, msg);
            return wrap;
        })());
        
        try {
            // Generate patient identification markdown
            // run all markdown generators in parallel when possible
            const [patientMarkdown, analysesMarkdown, epicrisisMarkdown] = await Promise.all([
                generatePatientMarkdown(patientData),
                analysesData ? populateAnalysesMarkdown(analysesData) : Promise.resolve(''),
                generateEpicrisisMarkdown(patientData)
            ]);

            log('Generated patient markdown content:', patientMarkdown);
            log('Generated analyses markdown content:', analysesMarkdown);
            log('Generated epicrisis markdown content:', epicrisisMarkdown);
            
            // Combine: patient → discharge summaries → imaging studies
            const combinedMarkdown = patientMarkdown + epicrisisMarkdown + analysesMarkdown;
            log('Combined markdown content:', combinedMarkdown);
            
            // Convert markdown to HTML using marked.js
            const htmlContent = marked.parse(combinedMarkdown);
            log('Converted markdown to HTML:', htmlContent);
            
            // Display the content and stash raw markdown for clipboard
            markdownContainer.innerHTML = htmlContent;
            markdownContainer.dataset.markdown = combinedMarkdown;
            log('Patient report data displayed successfully');
            
        } catch (error) {
            console.error('Error displaying patient report:', error);
            markdownContainer.replaceChildren((() => {
                const wrap = document.createElement('div');
                wrap.className = 'error-content';
                const icon = document.createElement('i');
                icon.className = 'fas fa-exclamation-triangle';
                const msg = document.createElement('p');
                msg.textContent = 'Error loading patient report data';
                wrap.append(icon, msg);
                return wrap;
            })());
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
    
    
    function loadRecentSearches() {
        const recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        if (!elements.recentSearchesList) return;
        elements.recentSearchesList.innerHTML = '';
        recentSearches.forEach(search => {
            const searchTerm = typeof search === 'string' ? search : search.term;
            const patientName = typeof search === 'object' ? search.patientName : null;
            const type = typeof search === 'object' ? search.type : 'unknown';

            const typeIcons = { cnp: 'fa-id-card', partial_cnp: 'fa-search', code: 'fa-barcode', name: 'fa-user', unknown: 'fa-question' };
            const tmpl = document.getElementById('recent-item-template');
            const div = tmpl.content.cloneNode(true).querySelector('.recent-item');
            div.title = `Search: ${searchTerm}`;
            div.querySelector('i').className = `fas ${typeIcons[type] || 'fa-question'}`;
            div.querySelector('span').textContent = patientName ? `${searchTerm} — ${patientName}` : searchTerm;
            div.querySelector('button').setAttribute('aria-label', `Search ${searchTerm}`);

            const trigger = () => { elements.cnpInput.value = searchTerm; elements.form.dispatchEvent(new Event('submit')); };
            div.addEventListener('click', trigger);
            // Stop button clicks from bubbling to the div and triggering twice
            div.querySelector('button').addEventListener('click', e => { e.stopPropagation(); trigger(); });

            elements.recentSearchesList.appendChild(div);
        });
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
    
    function showLoading() {
        elements.loadingOverlay.style.display = 'flex';
        elements.analyzeBtn.disabled = true;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
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

        log('Patient data display completed');
    }
    
    // Enhanced patient basic info display
    function displayPatientBasicInfo(patientData) {
        log('Displaying patient basic info:', patientData);
        
        // Patient Name
        const name = formatPatientName(patientData.name);
        const headingEl = elements.patientName?.querySelector('#patient-tab-heading');
        if (headingEl) headingEl.textContent = name;
        log('Patient name set to:', name);
        
        // Meta badges (id, gender, age)
        const age = calculateAge(patientData.birthDate);
        if (elements.patientId)     elements.patientId.textContent     = patientData.id ? `ID: ${patientData.id}` : '';
        if (elements.patientGender) elements.patientGender.textContent = formatGender(patientData.gender);
        if (elements.patientAge)    elements.patientAge.textContent    = age !== 'N/A' ? `${age} years` : '';

        if (elements.patientAvatar) {
            const ageNum = age !== 'N/A' ? parseInt(age, 10) : null;
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
        log('CNP:', cnp, 'Phone:', contactInfo.phone, 'Email:', contactInfo.email);
    }
    
    // Enhanced name formatting
    function formatPatientName(nameArray) {
        if (!nameArray) return 'N/A';
        const arr = Array.isArray(nameArray) ? nameArray : [nameArray];
        if (arr.length === 0) return 'N/A';
        const name = arr[0];
        const family = name.family || '';
        const given = name.given ? name.given.join(' ') : '';
        
        if (family && given) {
            return `${family}, ${given}`;
        } else if (family) {
            return family;
        } else if (given) {
            return given;
        }
        
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
        // Parse YYYY-MM-DD directly to avoid UTC-offset day shift from new Date()
        const parts = String(birthDate).split('-').map(Number);
        if (parts.length < 2 || isNaN(parts[0])) return 'N/A';
        const [year, month, day = 1] = parts;
        const today = new Date();
        let age = today.getFullYear() - year;
        const m = today.getMonth() + 1 - month;
        if (m < 0 || (m === 0 && today.getDate() < day)) age--;
        return age >= 0 ? age : 'N/A';
    }
    
    // Function to view imaging study
    async function viewImagingStudy(studyId, reportId) {
        try {
            // Fetch imaging study data using FHIR API
            const studyResponse = await fetch(`/fhir/ImagingStudy/${studyId}`);
            
            if (!studyResponse.ok) {
                if (studyResponse.status === 401) {
                    showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                    return;
                }
                showToast(`Error loading imaging study ${studyId}`, 'error');
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
            closeImagingStudyModal();
        });
        
        // Add event listeners for closing the modal
        const closeButtons = modal.querySelectorAll('[data-close-modal], .close');
        closeButtons.forEach(button => {
            button.addEventListener('click', () => {
                document.body.removeChild(modal);
            });
        });
        
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
            modal.remove();
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
        radio: { icon: 'fa-x-ray',      label: 'X-Ray' },
        ct:    { icon: 'fa-computer',   label: 'CT Scan' },
        irm:   { icon: 'fa-magnet',     label: 'MRI' },
        eco:   { icon: 'fa-heartbeat',  label: 'Ultrasound' },
        rads:  { icon: 'fa-radiation',  label: 'Fluoroscopy' },
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
        if (iconEl) iconEl.className = `fas ${modality.icon}`;

        const typeText = article.querySelector('.type-text');
        if (typeText) typeText.textContent = analysisText || modality.label;

        const reportId = article.querySelector('.report-id');
        if (reportId) reportId.textContent = `#${serviceRequest.id}`;

        const examDateEl = article.querySelector('.exam-date');
        if (examDateEl) examDateEl.textContent = serviceRequest.authoredOn ? formatExamDate(serviceRequest.authoredOn) : '';

        // Ordering physician (from ServiceRequest.requester)
        const referrer = serviceRequest.requester?.display;
        const referrerEl = article.querySelector('.card-referrer');
        if (referrerEl && referrer) referrerEl.textContent = referrer;

        // Request metadata: clinical indication + note
        const metaDl = article.querySelector('.request-meta');
        if (metaDl) {
            const indication = serviceRequest.reason?.[0]?.display
                || serviceRequest.reasonCode?.[0]?.text
                || serviceRequest.reasonCode?.[0]?.coding?.[0]?.display;
            const note = serviceRequest.note?.[0]?.text;
            const info = serviceRequest.supportingInfo?.[0]?.display;
            const addMeta = (label, value) => {
                if (!value) return;
                const dt = document.createElement('dt');
                dt.textContent = label;
                const dd = document.createElement('dd');
                dd.textContent = value;
                metaDl.append(dt, dd);
            };
            addMeta('Indication', indication);
            addMeta('Clinical note', note || info);
        }

        return article;
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

            // Reporting physician + report date
            const physician = data.resultsInterpreter?.[0]?.display
                || data.performer?.[0]?.actor?.display || '';
            const date = data.started || data.effectiveDateTime || data.authoredOn || '';
            const medicEl = article.querySelector('.card-medic');
            if (medicEl && physician) medicEl.textContent = physician;
            const dateEl = article.querySelector('.report-date');
            if (dateEl && date) dateEl.textContent = formatDate(date);

            // Report text
            const reportPreview = article.querySelector('.report-preview');
            if (reportPreview) {
                const forms = data.presentedForm || [];
                const notes = data.note || [];
                if (forms.length > 0) {
                    if (forms.length > 1) {
                        const typeTextEl = article.querySelector('.type-text');
                        if (typeTextEl) {
                            const titles = forms.map(f => f.title).filter(Boolean);
                            if (titles.length > 1) typeTextEl.textContent = titles.join(' / ');
                        }
                    }
                    for (const form of forms) {
                        if (forms.length > 1 && form.title) {
                            const h5 = document.createElement('h5');
                            h5.className = 'study-title';
                            h5.textContent = form.title;
                            reportPreview.appendChild(h5);
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
                    for (const note of notes) {
                        if (note.text) {
                            const div = document.createElement('div');
                            div.className = 'report-note';
                            div.innerHTML = marked.parse(note.text);
                            reportPreview.appendChild(div);
                        }
                    }
                } else if (data.conclusion) {
                    const div = document.createElement('div');
                    div.innerHTML = marked.parse(data.conclusion);
                    reportPreview.appendChild(div);
                } else {
                    reportPreview.innerHTML = '<p class="no-report-text">No report text available yet</p>';
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
            if (reportPreview) reportPreview.innerHTML = '';
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

        // Build a single markdown document for all encounters
        let markdown = '';
        valid.forEach((item, index) => {
            const enc = item.enc;
            const epicrisisText = extractEpicrisisText(enc);
            const diagnosis = extractDiagnosisText(enc) || 'Epicrisis';
            const meta = [];
            if (enc.period?.start) meta.push(`**Admission:** ${formatDate(enc.period.start)}`);
            if (enc.period?.end)   meta.push(`**Discharge:** ${formatDate(enc.period.end)}`);
            const attender = enc.participant?.find(p =>
                p.type?.some(t => t.coding?.some(c => c.code === 'ATND'))
            );
            if (attender?.individual?.display) meta.push(`**Attending:** ${attender.individual.display}`);
            if (enc.serviceType?.display) meta.push(`**Service:** ${enc.serviceType.display}`);

            if (valid.length === 1) {
                markdown += `# ${diagnosis}\n\n`;
            } else {
                markdown += `## ${index + 1}. ${diagnosis}\n\n`;
            }
            if (meta.length) markdown += `${meta.join(' · ')}  \n\n`;
            markdown += epicrisisText.trim() + '\n\n';
            if (index < valid.length - 1) markdown += '---\n\n';
        });

        const htmlContent = marked.parse(markdown);
        elements.epicrisisContent.innerHTML = htmlContent;
        elements.epicrisisContent.dataset.markdown = markdown;
    }
    
    const SCHEDULE_STATUS_CLASS = {
        'on-hold':        'status-pending',
        'draft':          'status-sent',
        'active':         'status-active',
        'completed':      'status-done',
        'ended':          'status-revoked',
        'revoked':        'status-revoked',
        'entered-in-error': 'status-error',
        'unknown':        'status-pending',
    };

    let scheduleEntries = [];

    async function showRequestModal(requestId, requestCode, patientName, modality, triggerEl) {
        const tmpl = document.getElementById('schedule-request-modal-template');
        if (!tmpl) return;
        const modal = tmpl.content.cloneNode(true).querySelector('dialog');

        modal.querySelector('.modal-request-code').textContent = requestCode;

        const metaDl  = modal.querySelector('.report-modal-meta');
        const bodyDiv = modal.querySelector('.report-modal-body');

        const originalText = triggerEl.textContent;
        triggerEl.textContent = '…';
        triggerEl.disabled = true;

        function addMeta(label, value) {
            if (!value) return;
            const item = document.createElement('span');
            item.className = 'meta-item';
            const dt = document.createElement('dt');
            dt.textContent = label;
            const dd = document.createElement('dd');
            dd.textContent = value;
            item.appendChild(dt);
            item.appendChild(dd);
            metaDl.appendChild(item);
        }

        function renderReportContent(reportData, isImaging) {
            bodyDiv.innerHTML = '';
            bodyDiv.classList.remove('report-empty');
            const forms = reportData.presentedForm || [];
            const notes = reportData.note || [];

            if (forms.length > 0) {
                for (const form of forms) {
                    if (form.title && forms.length > 1) {
                        const h = document.createElement('h3');
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
            } else if (isImaging && notes.length > 0) {
                for (const note of notes) {
                    if (!note.text) continue;
                    const div = document.createElement('div');
                    div.innerHTML = marked.parse(note.text);
                    bodyDiv.appendChild(div);
                }
            } else if (reportData.conclusion) {
                bodyDiv.innerHTML = marked.parse(reportData.conclusion);
            } else {
                bodyDiv.classList.add('report-empty');
                bodyDiv.textContent = 'No report text available yet.';
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

        // Show modal immediately with meta we already have from the schedule row
        addMeta('Patient', patientName);
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
                // Enrich meta from report data
                const date = reportData.started || reportData.effectiveDateTime || reportData.authoredOn;
                if (date) addMeta('Date', formatDateWithTime(date));
                const performer = reportData.performer?.[0]?.actor?.display
                    || reportData.resultsInterpreter?.[0]?.display;
                if (performer) addMeta('Physician', performer);
                renderReportContent(reportData, isImaging);
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
        fetchSchedule(start, end, force, patientText, labId, sectionName);
    }

    async function fetchSchedule(startDate, endDate, force = false, patientText = null, labId = null, sectionName = null) {
        if (!elements.scheduleBody) return;
        const params = new URLSearchParams();
        if (startDate)   params.set('start_date', startDate);
        if (endDate)     params.set('end_date', endDate);
        if (force)       params.set('refresh', '1');
        if (patientText) params.set('patient_text', patientText);
        if (labId)       params.set('lab_id', labId);
        if (sectionName) params.set('section_name', sectionName);
        const url = `/fhir/Schedule${params.toString() ? '?' + params.toString() : ''}`;
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
        }
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
    }

    function renderSchedule() {
        if (!elements.scheduleBody) return;

        elements.scheduleBody.innerHTML = '';
        if (scheduleEntries.length === 0) {
            if (elements.scheduleTable) elements.scheduleTable.hidden = true;
            if (elements.noSchedule) elements.noSchedule.style.display = '';
            return;
        }

        if (elements.noSchedule) elements.noSchedule.style.display = 'none';
        scheduleEntries.forEach(r => {
            const authoredOn = r.authoredOn || '';
            const isMultiDay = (elements.scheduleStartDate?.value || '') !== (elements.scheduleEndDate?.value || '');
            const time = isMultiDay ? authoredOn : (authoredOn.includes(' ') ? authoredOn.split(' ')[1] : authoredOn);
            const patientName = r.subject?.display || '';
            const requestCode = r.identifier?.[0]?.value || r.id || '';
            const section = r.note?.[0]?.text || '';
            const requestedBy = r.requester?.display || '';
            const laboratory = r.code?.text || '';
            const status = r.status || '';
            const statusClass = SCHEDULE_STATUS_CLASS[status] || '';

            const tr = document.createElement('tr');

            // Time
            const timeTd = document.createElement('td');
            timeTd.textContent = time;
            tr.appendChild(timeTd);

            // Patient name — clickable, resolves patient ID via request page
            const nameTd = document.createElement('td');
            const nameBtn = document.createElement('button');
            nameBtn.className = 'schedule-patient-link';
            nameBtn.textContent = patientName;
            nameBtn.title = `Load patient record for ${patientName}`;
            nameBtn.addEventListener('click', () => loadPatientFromRequest(r.id, patientName, nameBtn));
            nameTd.appendChild(nameBtn);
            tr.appendChild(nameTd);

            // Request code — opens request detail modal
            const codeTd = document.createElement('td');
            const codeBtn = document.createElement('button');
            codeBtn.className = 'schedule-patient-link';
            codeBtn.textContent = requestCode;
            codeBtn.title = `View request details (${requestCode})`;
            codeBtn.addEventListener('click', () => showRequestModal(r.id, requestCode, patientName, r.category?.[0]?.coding?.[0]?.code || '', codeBtn));
            codeTd.appendChild(codeBtn);
            tr.appendChild(codeTd);

            // Remaining plain cells
            [section, requestedBy, laboratory].forEach(val => {
                const td = document.createElement('td');
                td.textContent = val;
                tr.appendChild(td);
            });

            // Status badge
            const statusTd = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = `schedule-status ${statusClass}`;
            badge.textContent = status;
            statusTd.appendChild(badge);
            tr.appendChild(statusTd);

            elements.scheduleBody.appendChild(tr);
        });
        if (elements.scheduleTable) elements.scheduleTable.hidden = false;
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
