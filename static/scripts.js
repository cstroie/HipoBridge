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
        patientName: document.getElementById('patientName'),
        patientCnp: document.getElementById('patientCnp'),
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
        printPatientBtn: document.getElementById('printPatientBtn'),
        // Analyses actions
        analysesSearch: document.getElementById('analysesSearch'),
        analysesFilter: document.getElementById('analysesFilter'),
        // Epicrisis actions
        // Loading overlay
        loadingOverlay: document.getElementById('loadingOverlay'),
        // Recent searches
        recentSearchesList: document.getElementById('recentSearchesList')
    };
    
    // Simple in-memory cache for encounters and reports to avoid duplicate network calls
    const cache = {
        encounters: {},
        reports: {}
    };

    // debug logging helper (set DEBUG=true during development to see logs)
    const DEBUG = false;
    function log(...args) { if (DEBUG) console.log(...args); }

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
        
        const themeIcon = elements.themeToggle.querySelector('i');
        themeIcon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
    
    function initializeTabs() {
        elements.tabContents.forEach(tab => {
            if (!tab.classList.contains('active')) {
                tab.style.display = 'none';
            }
        });
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
        
        // Patient actions
        if (elements.printPatientBtn) {
            elements.printPatientBtn.addEventListener('click', printPatientData);
        }
        
        // Epicrisis tab buttons
        if (elements.copyEpicrisisBtn) {
            elements.copyEpicrisisBtn.addEventListener('click', copyEpicrisisMarkdown);
        }

        // Report tab buttons
        if (elements.copyReportBtn) {
            elements.copyReportBtn.addEventListener('click', copyReportMarkdown);
        }
    }
    
    function switchTab(tabId) {
        // Update active nav item and aria-selected
        elements.navItems.forEach(nav => {
            nav.classList.remove('active');
            nav.setAttribute('aria-selected', 'false');
        });
        const activeNavItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
        if (activeNavItem) {
            activeNavItem.classList.add('active');
            activeNavItem.setAttribute('aria-selected', 'true');
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
        
        // Notify user of search start
        showToast('Starting patient search...', 'info');
        
        try {
            // Enhanced search with better error handling
            log('Starting patient search...');
            const searchResult = await performPatientSearch(cnp);
            log('Patient search result:', searchResult);
            
            if (!searchResult.success) {
                showToast(searchResult.message, 'error');
                return;
            }
            
            const { patientData, patientCode } = searchResult;
            log('Patient data retrieved:', patientData);
            log('Patient code:', patientCode);
            
            // Get analyses using FHIR API with better error handling
            log('Fetching analyses data for patient:', patientCode);
            const analysesResult = await fetchAnalysesData(patientCode);
            log('Analyses data result:', analysesResult);
            
            if (!analysesResult.success) {
                showToast(analysesResult.message, 'error');
                return;
            }
            
            const analysesData = analysesResult.data;
            log('Analyses data retrieved:', analysesData);
            
            // Display patient data first
            log('Displaying patient data...');
            await displayPatientData(patientData, analysesData);
            
            // Load and display reports first, then epicrisis, then report
            log('Loading and displaying reports...');
            await loadAndDisplayReports(analysesData, patientData);
            log('Loading and displaying epicrisis...');
            await loadAndDisplayEpicrisis(patientData);
            log('Loading and displaying report...');
            await loadAndDisplayReport(patientData, analysesData);
            
            // Switch to patient profile tab with enhanced navigation
            log('Switching to patient tab...');
            switchToPatientTab();
            
            showToast('Analysis loading complete', 'success');
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
        
        // CNP validation (13 digits)
        if (/^\d{13}$/.test(trimmed)) {
            return { 
                isValid: true, 
                type: 'cnp', 
                message: 'Valid CNP format detected.' 
            };
        }
        
        // Partial CNP validation (digits followed by *)
        if (/^\d+\*$/.test(trimmed)) {
            return { 
                isValid: true, 
                type: 'partial_cnp', 
                message: 'Partial CNP format detected.' 
            };
        }
        
        // Patient code validation (alphanumeric with common patterns)
        if (/^[A-Za-z0-9\-_]+$/.test(trimmed)) {
            return { 
                isValid: true, 
                type: 'code', 
                message: 'Patient code format detected.' 
            };
        }
        
        // Patient name validation (letters, spaces, hyphens)
        if (/^[A-Za-z\s\-\'\.]+$/.test(trimmed)) {
            return { 
                isValid: true, 
                type: 'name', 
                message: 'Patient name format detected.' 
            };
        }
        
        return { 
            isValid: false, 
            message: 'Invalid format. Please enter a valid CNP, partial CNP, patient code, or patient name.' 
        };
    }
    
    // Enhanced patient search function
    async function performPatientSearch(identifier) {
        try {
            const validation = validatePatientIdentifier(identifier);
            
            // Show appropriate message based on search type
            if (validation.type === 'cnp') {
                showToast('Validating CNP...', 'info');
                // CNP validation can be added here if needed
            } else if (validation.type === 'partial_cnp') {
                showToast('Searching with partial CNP...', 'info');
            } else if (validation.type === 'code') {
                showToast('Searching by patient code...', 'info');
            } else {
                showToast('Searching by patient name...', 'info');
            }
            
            // Search for patient using FHIR API
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
            
            // Handle different response types
            if (searchData.resourceType === "Patient") {
                // Single patient
                patientCode = searchData.id;
                patientData = searchData;
            } else if (searchData.resourceType === "Bundle" && searchData.entry && searchData.entry.length > 0) {
                // Multiple patients - use the first one
                const firstPatient = searchData.entry[0].resource;
                patientCode = firstPatient.id;
                
                // Get full patient data using FHIR API
                const patientResponse = await fetch(`/fhir/Patient/${patientCode}`);
                if (patientResponse.ok) {
                    patientData = await patientResponse.json();
                } else {
                    patientData = firstPatient;
                }
                
                // Show message if multiple patients found
                if (searchData.entry.length > 1) {
                    showToast(`Found ${searchData.entry.length} patients. Showing the first result.`, 'info');
                }
            } else {
                return {
                    success: false,
                    message: 'No patient data found.'
                };
            }
            
            if (!patientCode || !patientData) {
                return {
                    success: false,
                    message: 'Failed to retrieve patient data.'
                };
            }
            
            showToast('Patient information retrieved successfully', 'success');
            
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
    async function fetchAnalysesData(patientCode) {
        try {
            showToast('Loading diagnostic reports...', 'info');
            
            const analysesResponse = await fetch(`/fhir/ServiceRequest?patient=${patientCode}&full=yes`);
            
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
            showToast('Patient diagnostic reports loaded successfully', 'success');
            
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
    
    // Enhanced tab switching function
    function switchToPatientTab() {
        log('Switching to patient tab');
        
        // Update navigation
        elements.navItems.forEach(nav => nav.classList.remove('active'));
        const patientNavItem = document.querySelector('.nav-item[data-tab="patient"]');
        if (patientNavItem) {
            patientNavItem.classList.add('active');
            log('Patient nav item activated');
        }
        
        // Show relevant tabs
        const tabsToShow = ['patient', 'analyses', 'epicrisis', 'report'];
        tabsToShow.forEach(tabName => {
            const tabElement = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
            if (tabElement) {
                tabElement.style.display = 'block';
                log(`Tab ${tabName} made visible`);
            }
        });
        
        // Update tab content display
        elements.tabContents.forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
            tab.hidden = true;
        });
        
        const patientTab = document.getElementById('patient-tab');
        if (patientTab) {
            patientTab.classList.add('active');
            patientTab.style.display = 'block';
            patientTab.hidden = false;
            log('Patient tab content activated and displayed');
        }
        
        // Also show the other tabs that should be visible after patient data is loaded
        const analysesTab = document.getElementById('analyses-tab');
        if (analysesTab) {
            analysesTab.hidden = false;
        }
        
        const epicrisisTab = document.getElementById('epicrisis-tab');
        if (epicrisisTab) {
            epicrisisTab.hidden = false;
        }
        
        const reportTab = document.getElementById('report-tab');
        if (reportTab) {
            reportTab.hidden = false;
        }
    }
    
    function hideLoading() {
        elements.loadingOverlay.style.display = 'none';
        elements.analyzeBtn.disabled = false;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }
    
    function clearResults() {
        // Clear patient data with null checks
        if (elements.patientId) elements.patientId.textContent = '';
        if (elements.patientName) elements.patientName.textContent = '';
        if (elements.patientCnp) elements.patientCnp.textContent = '';
        if (elements.patientGender) elements.patientGender.textContent = '';
        if (elements.patientBirthDate) elements.patientBirthDate.textContent = '';
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
        
        // Hide navigation tabs for patient data
        elements.navItems.forEach(item => {
            if (item.getAttribute('data-tab') !== 'search') {
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
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        const themeIcon = elements.themeToggle.querySelector('i');
        themeIcon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        
        showToast(`Theme switched to ${newTheme}`, 'info');
    }
    
    
    function filterAnalyses() {
        const searchTerm = elements.analysesSearch ? elements.analysesSearch.value.toLowerCase() : '';
        const filterType = elements.analysesFilter ? elements.analysesFilter.value : 'all';
        
        const cards = elements.analysesGrid.querySelectorAll('.analysis-card');
        cards.forEach(card => {
            const type = card.className.match(/radio|ct|irm|eco|rads/)?.[0] || '';
            const text = card.textContent.toLowerCase();
            
            const matchesSearch = searchTerm ? text.includes(searchTerm) : true;
            const matchesType = filterType === 'all' || type === filterType;
            
            card.style.display = matchesSearch && matchesType ? 'block' : 'none';
        });
    }
    
    function printPatientData() {
        window.print();
    }
    
    async function copyEpicrisisMarkdown() {
        const markdown = elements.epicrisisContent?.dataset.markdown;
        if (!markdown) {
            showToast('No epicrisis content to copy', 'warning');
            return;
        }

        const confirm = () => {
            const btn = elements.copyEpicrisisBtn;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> <span>Copied!</span>';
            setTimeout(() => { btn.innerHTML = originalHTML; }, 2000);
        };

        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(markdown);
                confirm();
                return;
            } catch (err) { /* fall through */ }
        }

        const ta = document.createElement('textarea');
        ta.value = markdown;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        ok ? confirm() : showToast('Failed to copy to clipboard', 'error');
    }
    
    async function copyReportMarkdown() {
        const markdown = elements.patientReportMarkdown?.dataset.markdown;
        if (!markdown) {
            showToast('No report content to copy', 'warning');
            return;
        }

        const confirm = () => {
            const btn = elements.copyReportBtn;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> <span>Copied!</span>';
            setTimeout(() => { btn.innerHTML = originalHTML; }, 2000);
        };

        // Prefer modern clipboard API, fall back to execCommand for plain HTTP
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(markdown);
                confirm();
                return;
            } catch (err) { /* fall through */ }
        }

        // execCommand fallback
        const ta = document.createElement('textarea');
        ta.value = markdown;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        ok ? confirm() : showToast('Failed to copy to clipboard', 'error');
    }
    
    async function loadAndDisplayReport(patientData, analysesData) {
        log('Loading and displaying report data');
        
        // Display patient report with analyses and epicrisis
        await displayPatientReport(patientData, analysesData);
        
        // Update report tab data
        updateReportTabData(patientData, extractMedicalStats(patientData), analysesData);
                
        log('Report data loading complete');
    }
    
    async function populateAnalysesMarkdown(analysesData) {
        log('Populating analyses by modality');
        
        // Define modality mapping
        const modalityMap = {
            'radio': { name: 'Radiography', icon: 'fa-x-ray', color: '#36a2eb' },
            'ct': { name: 'CT Scan', icon: 'fa-computer', color: '#ff6384' },
            'irm': { name: 'MRI', icon: 'fa-magnet', color: '#ffce56' },
            'eco': { name: 'Ultrasound', icon: 'fa-heartbeat', color: '#4bc0c0' },
            'rads': { name: 'Radiology', icon: 'fa-radiation', color: '#9966ff' }
        };
        
        // Group analyses by modality
        const analysesByModality = {};
        
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            analysesData.entry.forEach(entry => {
                const serviceRequest = entry.resource;
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                const analysisText = serviceRequest.code?.coding?.[0]?.display || 'analysis';
                const examDate = serviceRequest.authoredOn ? new Date(serviceRequest.authoredOn) : null;
                
                // Skip unknown types
                if (!modalityMap[analysisType]) return;
                
                if (!analysesByModality[analysisType]) {
                    analysesByModality[analysisType] = [];
                }
                
                analysesByModality[analysisType].push({
                    serviceRequest,
                    analysisText,
                    examDate,
                    examDateString: serviceRequest.authoredOn
                });
            });
        }
        
        // Sort each modality group by date (most recent first)
        Object.keys(analysesByModality).forEach(modality => {
            analysesByModality[modality].sort((a, b) => {
                if (!a.examDate || !b.examDate) return 0;
                return b.examDate - a.examDate;
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
                analyses.map(a => a.serviceRequest.id),
                MAX_CONCURRENT_REQUESTS,
                id => getReportContent(id)
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
    async function getReportContent(serviceRequestId) {
        // check cache first
        if (cache.reports[serviceRequestId]) {
            return cache.reports[serviceRequestId];
        }

        try {
            const reportResponse = await fetch(`/fhir/DiagnosticReport/${serviceRequestId}`);
            
            if (!reportResponse.ok) {
                log(`Report not found for service request ${serviceRequestId}`);
                return null;
            }
            
            const reportData = await reportResponse.json();
            let content = null;
            // Extract report content from different possible sources
            if (reportData.conclusion) {
                content = reportData.conclusion;
            } else if (reportData.presentedForm && reportData.presentedForm.length > 0) {
                // Concatenate all presented form content
                content = '';
                reportData.presentedForm.forEach(form => {
                    if (form.data) {
                        content += form.data + '\n\n';
                    }
                });
                content = content.trim();
            } else if (reportData.result && reportData.result.length > 0) {
                // Fallback to result array
                content = '';
                reportData.result.forEach(result => {
                    if (result.display) {
                        content += result.display + '\n\n';
                    }
                });
                content = content.trim();
            }

            // cache result (even if null to avoid repeated attempts)
            cache.reports[serviceRequestId] = content;
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
                admissionDate: encounterData.period?.start ? new Date(encounterData.period.start) : null,
                dischargeDate: encounterData.period?.end   ? new Date(encounterData.period.end)   : null,
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
            return b.dischargeDate - a.dischargeDate;
        });

        if (epicrisisData.length === 0) return '';

        let markdown = '## Discharge Summaries\n\n';

        epicrisisData.forEach((ep, index) => {
            const dischargeStr  = ep.dischargeDate  ? formatDate(ep.dischargeDate.toISOString())  : 'unknown';
            const admissionStr  = ep.admissionDate  ? formatDate(ep.admissionDate.toISOString())  : 'unknown';
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
        
        // Show loading state
        const markdownContainer = elements.patientReportMarkdown;
        markdownContainer.innerHTML = `
            <div class="loading-content">
                <i class="fas fa-spinner fa-spin"></i>
                <p>Loading patient report data...</p>
            </div>
        `;
        
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
            markdownContainer.innerHTML = `
                <div class="error-content">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Error loading patient report data</p>
                </div>
            `;
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
            // store in cache
            cache.encounters[checkoutId] = encounterData;
            log(`Encounter data fetched successfully for checkout ${checkoutId}:`, encounterData);
            return encounterData;
            
        } catch (error) {
            console.error(`Error fetching encounter data for checkout ${checkoutId}:`, error);
            return null;
        }
    }
    
    // Helper function to extract checkout diagnosis from encounter data
    function extractCheckoutDiagnosis(encounterData) {
        if (!encounterData || !encounterData.diagnosis || encounterData.diagnosis.length === 0) {
            return null;
        }
        
        // Look for discharge diagnosis first (use code "DD")
        const dischargeDiagnosis = encounterData.diagnosis.find(d => 
            d.use && d.use.coding && d.use.coding.some(c => c.code === "DD")
        );
        
        if (dischargeDiagnosis && dischargeDiagnosis.condition && dischargeDiagnosis.condition.display) {
            return dischargeDiagnosis.condition.display;
        }
        
        // Fallback to first diagnosis if no discharge diagnosis found
        const firstDiagnosis = encounterData.diagnosis[0];
        if (firstDiagnosis.condition && firstDiagnosis.condition.display) {
            return firstDiagnosis.condition.display;
        }
        
        return null;
    }
    
    function loadRecentSearches() {
        const recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        if (elements.recentSearchesList) {
            elements.recentSearchesList.innerHTML = '';
            recentSearches.forEach(search => {
                const div = document.createElement('div');
                div.className = 'recent-item';
                
                const displayText = formatRecentSearchDisplay(search);
                const searchTerm = typeof search === 'string' ? search : search.term;
                
                div.innerHTML = `
                    <span>${displayText}</span>
                    <button class="btn-icon btn-small" onclick="searchFromRecent('${searchTerm}')" title="Search for ${searchTerm}">
                        <i class="fas fa-search"></i>
                    </button>
                `;
                elements.recentSearchesList.appendChild(div);
            });
        }
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
        if (/^\d{13}$/.test(searchTerm)) return 'cnp';
        if (/^\d+\*$/.test(searchTerm)) return 'partial_cnp';
        if (/^[A-Za-z0-9\-_]+$/.test(searchTerm)) return 'code';
        if (/^[A-Za-z\s\-\'\.]+$/.test(searchTerm)) return 'name';
        return 'unknown';
    }
    
    // Make function available globally
    window.searchFromRecent = function(searchTerm) {
        elements.cnpInput.value = searchTerm;
        elements.form.dispatchEvent(new Event('submit'));
    };
    
    // Function to format recent search display
    function formatRecentSearchDisplay(searchItem) {
        if (typeof searchItem === 'string') {
            // Legacy format - just the search term
            return searchItem;
        }
        
        // New format - rich search object
        let displayText = searchItem.term;
        
        // Add patient name if available
        if (searchItem.patientName) {
            displayText += ` - ${searchItem.patientName}`;
        }
        
        // Add type indicator
        const typeIcons = {
            'cnp': 'fa-id-card',
            'partial_cnp': 'fa-search',
            'code': 'fa-barcode',
            'name': 'fa-user',
            'unknown': 'fa-question'
        };
        
        const typeIcon = typeIcons[searchItem.type] || 'fa-question';
        displayText = `<i class="fas ${typeIcon}"></i> ${displayText}`;
        
        return displayText;
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
        
        // Use template for toast
        const toastTemplate = document.getElementById('toast-template');
        const toast = toastTemplate.content.cloneNode(true).querySelector('.toast');
        toast.className = `toast toast-${type}`;
        
        // Add icon based on type
        const iconMap = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };
        
        const icon = iconMap[type] || 'fa-check-circle';
        toast.innerHTML = `<i class="fas ${icon}"></i> ${message}`;
        
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
    
    // Enhanced loading states
    function showLoading(message = 'Loading patient data...') {
        elements.loadingOverlay.style.display = 'flex';
        elements.analyzeBtn.disabled = true;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
        
        // Update loading message if provided
        const loadingMessage = document.querySelector('.loading-spinner p');
        if (loadingMessage) {
            loadingMessage.textContent = message;
        }
    }
    
    // Markdown to HTML conversion now uses marked.js library
    // marked.parse(markdownText) converts markdown to HTML

    function displayPatientData(patientData, analysesData, epicrisisData = null) {
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
        
        // Patient ID
        elements.patientId.textContent = patientData.id || 'N/A';
        log('Patient ID set to:', elements.patientId.textContent);
        
        // Patient Name with enhanced formatting
        const name = formatPatientName(patientData.name);
        elements.patientName.innerHTML = `<i class="fas fa-user"></i> ${name}`;
        log('Patient name set to:', name);
        
        // Set age in the existing age badge
        const age = calculateAge(patientData.birthDate);
        const ageBadge = document.querySelector('#patientAge');
        if (ageBadge) {
            ageBadge.textContent = `Age: ${age}`;
        }
        log('Age set to:', age);
        
        // CNP with validation
        const cnp = extractCNP(patientData.identifier);
        elements.patientCnp.textContent = cnp || 'N/A';
        log('CNP set to:', cnp);
        
        // Gender with icons
        const gender = formatGender(patientData.gender);
        elements.patientGender.textContent = gender;
        log('Gender set to:', gender);
        
        // Birth date with formatting
        elements.patientBirthDate.textContent = formatBirthDate(patientData.birthDate);
        log('Birth date set to:', elements.patientBirthDate.textContent);
        
        // Contact information
        const contactInfo = extractContactInfo(patientData.telecom);
        elements.patientPhone.textContent = contactInfo.phone || 'N/A';
        elements.patientEmail.textContent = contactInfo.email || 'N/A';
        log('Contact info set - Phone:', contactInfo.phone, 'Email:', contactInfo.email);
    }
    
    // Enhanced name formatting
    function formatPatientName(nameArray) {
        if (!nameArray || nameArray.length === 0) {
            return 'N/A';
        }
        
        const name = nameArray[0];
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
        const today = new Date();
        const birth = new Date(birthDate);
        let age = today.getFullYear() - birth.getFullYear();
        const monthDiff = today.getMonth() - birth.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
            age--;
        }
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
                }
                showToast(`Error loading imaging study ${studyId}`, 'error');
                return;
            }
            
            const studyData = await studyResponse.json();
            displayImagingStudyModal(studyData, studyId, reportId);
            showToast(`Imaging study ${studyId} loaded successfully`, 'success');
            
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
        
        // Set modal title
        modal.querySelector('h2').innerHTML = `<i class="fas fa-x-ray"></i> Imaging Study #${studyId}`;
        
        // Populate study information
        const studyInfo = modal.querySelector('.study-info');
        populateStudyInfo(studyInfo, studyData);
        
        // Populate series information
        const seriesList = modal.querySelector('.series-list');
        populateSeriesList(seriesList, studyData);
        
        // Set back to report link
        const backLink = modal.querySelector('.back-to-report');
        backLink.href = '#';
        backLink.innerHTML = `<i class="fas fa-arrow-left"></i> Back to Report #${reportId}`;
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
    
    // Helper function to populate study information
    function populateStudyInfo(studyInfo, studyData) {
        // Started date
        if (studyData.started) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-calendar"></i> Started:</strong> ${formatDateWithTime(studyData.started)}`;
            studyInfo.appendChild(p);
        }
        
        // Modality
        if (studyData.modality) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-stethoscope"></i> Modality:</strong> ${studyData.modality.display || studyData.modality.code || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Description
        if (studyData.description) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-file-medical"></i> Description:</strong> ${studyData.description}`;
            studyInfo.appendChild(p);
        }
        
        // Performer
        if (studyData.performer && studyData.performer.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-user-md"></i> Performer:</strong> ${studyData.performer[0].actor?.display || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Referrer
        if (studyData.referrer) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-user-check"></i> Referrer:</strong> ${studyData.referrer.display || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Reason
        if (studyData.reason && studyData.reason.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-question-circle"></i> Reason:</strong> ${studyData.reason[0].text || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Note
        if (studyData.note && studyData.note.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-sticky-note"></i> Note:</strong> ${studyData.note[0].text || 'N/A'}`;
            studyInfo.appendChild(p);
        }
    }
    
    // Helper function to populate series list
    function populateSeriesList(seriesList, studyData) {
        if (!studyData.series || studyData.series.length === 0) return;
        
        studyData.series.forEach((series, index) => {
            const li = document.createElement('li');
            li.innerHTML = `<strong><i class="fas fa-list-ol"></i> Series ${series.number || index + 1}:</strong> ${series.description || 'N/A'}`;
            if (series.modality) {
                li.innerHTML += ` (Modality: ${series.modality.display || series.modality.code || 'N/A'})`;
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
    async function loadAndDisplayReports(analysesData, patientData) {
        log('Loading and displaying reports:', analysesData);
        
        // Define the types of reports to include
        const includedTypes = ['radio', 'ct', 'irm', 'eco', 'rads'];
        
        // Check if we have a FHIR Bundle of ServiceRequests
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            // Filter entries to only include specified types
            const filteredEntries = analysesData.entry.filter(entry => {
                const serviceRequest = entry.resource;
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                return includedTypes.includes(analysisType);
            });
            
            if (filteredEntries.length === 0) {
                elements.noAnalyses.style.display = 'block';
                elements.analysesGrid.innerHTML = ''; // Clear any existing content
                log('No matching analyses found after filtering');
                return;
            }
            
            elements.noAnalyses.style.display = 'none';
            log('Found', filteredEntries.length, 'matching service requests');
            
            // Clear existing content
            elements.analysesGrid.innerHTML = '';
            
            // Process each filtered service request
            for (const entry of filteredEntries) {
                const serviceRequest = entry.resource;
                log('Processing service request:', serviceRequest);
                
                // Extract type and display text from service request code
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                const analysisText = serviceRequest.code?.coding?.[0]?.display || 'analysis';
                log('Analysis type:', analysisType, 'Text:', analysisText);
                
                // Create analysis card using template
                const analysisCard = createAnalysisCard(serviceRequest, analysisType, analysisText);
                log('Created analysis card:', analysisCard);
                
                // Fetch and display report content
                try {
                    // Fetch report data using FHIR API - now using the service request ID directly
                    log('Fetching diagnostic report for service request:', serviceRequest.id);
                    const reportResponse = await fetch(`/fhir/DiagnosticReport/${serviceRequest.id}`);
                    
                    if (reportResponse.ok) {
                        const reportData = await reportResponse.json();
                        log('Report data loaded for service request', serviceRequest.id, ':', reportData);
                        
                        // Add performer and interpreter to footer if available
                        const reportFooter = analysisCard.querySelector('.report-footer');
                        if (reportFooter && reportData.resultsInterpreter && reportData.resultsInterpreter.length > 0) {
                            // Add interpreter if available
                            const p = document.createElement('p');
                            p.innerHTML = `<strong><i class="fas fa-user-md"></i> Medic:</strong> ${reportData.resultsInterpreter[0].display || ''}`;
                            reportFooter.appendChild(p);
                        }
                        
                        // Add report content to the card - now using presentedForm or conclusion
                        const reportPreview = analysisCard.querySelector('.report-preview');
                        if (reportPreview) {
                            reportPreview.id = `report-${serviceRequest.id}`;
                            
                            if (reportData.presentedForm && reportData.presentedForm.length > 0) {
                                // Process all presentedForm entries
                                for (const form of reportData.presentedForm) {
                                    // Add a header for each result
                                    if (form.title) {
                                        const h5 = document.createElement('h5');
                                        h5.innerHTML = `<i class="fas fa-file-alt"></i> ${form.title}`;
                                        reportPreview.appendChild(h5);
                                    }
                                    
                                    if (form.contentType === 'text/plain' && form.data) {
                                        const pre = document.createElement('pre');
                                        pre.textContent = form.data;
                                        reportPreview.appendChild(pre);
                                    } else if (form.contentType === 'text/markdown' && form.data) {
                                        const htmlResult = marked.parse(form.data);
                                        const div = document.createElement('div');
                                        div.innerHTML = htmlResult;
                                        reportPreview.appendChild(div);
                                    } else if (form.contentType === 'text/html' && form.data) {
                                        const div = document.createElement('div');
                                        div.innerHTML = form.data;
                                        reportPreview.appendChild(div);
                                    }
                                }
                            } else if (reportData.conclusion) {
                                const htmlResult = marked.parse(reportData.conclusion);
                                const div = document.createElement('div');
                                div.innerHTML = htmlResult;
                                reportPreview.appendChild(div);
                            } else {
                                // If no content, show a message
                                const p = document.createElement('p');
                                p.textContent = 'No report content available';
                                reportPreview.appendChild(p);
                            }
                        }
                        
                        // Add link to ImagingStudy if available
                        const imagingStudyLink = analysisCard.querySelector('.imaging-study-link');
                        if (imagingStudyLink && reportData.imagingStudy) {
                            const studyId = reportData.imagingStudy.reference.split('/')[1];
                            const a = document.createElement('a');
                            a.href = '#';
                            a.innerHTML = `<i class="fas fa-x-ray"></i> View Imaging Study #${studyId}`;
                            a.addEventListener('click', function(e) {
                                e.preventDefault();
                                viewImagingStudy(studyId, serviceRequest.id);
                            });
                            imagingStudyLink.appendChild(a);
                        }
                    } else {
                        log('Error loading report data for service request', serviceRequest.id, ':', reportResponse.status);
                    }
                } catch (err) {
                    console.error('Error fetching report data:', err);
                }
                
                // Add the card to the grid
                log('Adding analysis card to grid');
                elements.analysesGrid.appendChild(analysisCard);
                
                // Force UI update to display the report immediately
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            
            log('Finished adding all analysis cards. Total cards:', elements.analysesGrid.children.length);
        } else {
            log('No analyses found, showing noAnalyses message');
            elements.noAnalyses.style.display = 'block';
            elements.analysesGrid.innerHTML = ''; // Clear any existing content
        }
    }
    
    const MODALITY_INFO = {
        radio: { icon: 'fa-x-ray',      label: 'X-Ray' },
        ct:    { icon: 'fa-computer',   label: 'CT Scan' },
        irm:   { icon: 'fa-magnet',     label: 'MRI' },
        eco:   { icon: 'fa-heartbeat',  label: 'Ultrasound' },
        rads:  { icon: 'fa-radiation',  label: 'Radiology' },
    };

    // Helper function to create analysis card
    function createAnalysisCard(serviceRequest, analysisType, analysisText) {
        log('Creating analysis card for:', serviceRequest, analysisType, analysisText);

        const cardTemplate = document.getElementById('analysis-card-template');
        if (!cardTemplate) {
            console.error('Analysis card template not found');
            return document.createElement('div');
        }

        const analysisCard = cardTemplate.content.cloneNode(true);
        const article = analysisCard.querySelector('article');
        if (!article) {
            console.error('Failed to clone analysis card template');
            return document.createElement('div');
        }

        article.className = `analysis-card ${analysisType}`;

        // Modality icon
        const modality = MODALITY_INFO[analysisType] || { icon: 'fa-file-medical', label: analysisText };
        const iconEl = article.querySelector('.modality-icon');
        if (iconEl) iconEl.className = `fas ${modality.icon}`;

        const typeText = article.querySelector('.type-text');
        if (typeText) typeText.textContent = analysisText || modality.label;

        const reportId = article.querySelector('.report-id');
        if (reportId) reportId.textContent = `#${serviceRequest.id}`;

        // Exam date
        const examDateElement = article.querySelector('.exam-date');
        if (examDateElement) {
            examDateElement.textContent = serviceRequest.authoredOn
                ? formatDateWithTime(serviceRequest.authoredOn)
                : 'Unknown';
        }

        // Status
        const statusElement = article.querySelector('.status');
        if (statusElement) statusElement.textContent = serviceRequest.status || 'Unknown';

        // Requesting medic
        const medicNameElement = article.querySelector('.medic-name');
        if (medicNameElement && serviceRequest.requester) {
            medicNameElement.textContent = serviceRequest.requester.display || '';
        }

        log('Analysis card created successfully');
        return article;
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
    
    // Function to load and display epicrisis progressively
    async function loadAndDisplayEpicrisis(patientData) {
        // Extract all checkout IDs from patient extensions
        const checkoutIds = extractCheckoutIds(patientData);
        
        if (checkoutIds.length === 0) return;
        
        // Try to fetch epicrisis data for each checkout ID until we find a valid one
        for (const checkoutId of checkoutIds) {
            const success = await loadEpicrisisForCheckout(checkoutId);
            if (success) {
                break; // Found a valid epicrisis, stop searching
            }
        }
    }
    
    // Helper function to extract checkout IDs from patient data
    function extractCheckoutIds(patientData) {
        if (!patientData.extension) return [];
        
        const checkoutExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkout-ids'));
        if (!checkoutExt || !checkoutExt.valueString) return [];
        
        return checkoutExt.valueString.split(',').filter(id => id.trim());
    }
    
    // Helper function to load epicrisis for a specific checkout
    async function loadEpicrisisForCheckout(checkoutId) {
        try {
            const encounterData = await fetchEncounterDataForCheckout(checkoutId);
            if (!encounterData) return false;
            const epicrisisText = extractEpicrisisText(encounterData);
            if (!epicrisisText) return false;
            await displayEpicrisisData(encounterData, epicrisisText);
            return true;
        } catch (err) {
            console.error('Error fetching encounter data:', err);
            return false;
        }
    }
    
    // Helper function to extract epicrisis text from encounter data
    function extractEpicrisisText(encounterData) {
        if (!encounterData.note || !Array.isArray(encounterData.note)) return '';
        
        // Concatenate all note texts
        return encounterData.note.map(note => note.text || '').join('\n\n');
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

    // Render encounterData + epicrisisText into the epicrisis markdown-content container
    function displayEpicrisisData(encounterData, epicrisisText) {
        const diagnosis = extractDiagnosisText(encounterData) || 'Epicrisis';

        // Build metadata line
        const meta = [];
        if (encounterData.period?.start) {
            const d = new Date(encounterData.period.start);
            meta.push(`**Admission:** ${d.toISOString().slice(0, 10)}`);
        }
        if (encounterData.period?.end) {
            const d = new Date(encounterData.period.end);
            meta.push(`**Discharge:** ${d.toISOString().slice(0, 10)}`);
        }
        const attender = encounterData.participant?.find(p =>
            p.type?.some(t => t.coding?.some(c => c.code === 'ATND'))
        );
        if (attender?.individual?.display) {
            meta.push(`**Attending:** ${attender.individual.display}`);
        }
        if (encounterData.serviceType?.display) {
            meta.push(`**Service:** ${encounterData.serviceType.display}`);
        }

        const markdown = `# ${diagnosis}\n\n${meta.join(' · ')}  \n\n${epicrisisText.trim()}`;

        const htmlContent = marked.parse(markdown);
        elements.epicrisisContent.innerHTML = htmlContent;
        elements.epicrisisContent.dataset.markdown = markdown;
    }
});
