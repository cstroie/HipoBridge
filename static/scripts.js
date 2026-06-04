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
        checkoutIdsList: document.getElementById('checkoutIdsList'),
        // Analyses tab elements
        analysesGrid: document.getElementById('analysesGrid'),
        noAnalyses: document.getElementById('noAnalyses'),
        // Epicrisis tab elements
        epicrisisContent: document.getElementById('epicrisisContent'),
        epicrisisDate: document.getElementById('epicrisisDate'),
        epicrisisTitle: document.getElementById('epicrisisTitle'),
        epicrisisFooter: document.getElementById('epicrisisFooter'),
        epicrisisSection: document.getElementById('epicrisisSection'),
        // Report tab elements
        patientReportMarkdown: document.getElementById('patientReportMarkdown'),
        reportPatientId: document.getElementById('reportPatientId'),
        reportPatientName: document.getElementById('reportPatientName'),
        reportPatientAge: document.getElementById('reportPatientAge'),
        reportPatientGender: document.getElementById('reportPatientGender'),
        copyReportBtn: document.getElementById('copyReportBtn'),
        // Dashboard elements
        patientChart: document.getElementById('patientChart'),
        activityList: document.getElementById('activityList'),
        alertsList: document.getElementById('alertsList'),
        upcomingList: document.getElementById('upcomingList'),
        // Header elements
        quickSearch: document.getElementById('quickSearch'),
        quickSearchBtn: document.getElementById('quickSearchBtn'),
        themeToggle: document.getElementById('themeToggle'),
        notificationsBtn: document.getElementById('notificationsBtn'),
        notificationBadge: document.getElementById('notificationBadge'),
        userMenuBtn: document.getElementById('userMenuBtn'),
        userDropdown: document.getElementById('userDropdown'),
        // Search examples
        exampleBtns: document.querySelectorAll('.example-btn'),
        // Header stats
        activePatientsCount: document.getElementById('activePatientsCount'),
        reportsToday: document.getElementById('reportsToday'),
        criticalCases: document.getElementById('criticalCases'),
        // Patient actions
        exportPatientBtn: document.getElementById('exportPatientBtn'),
        printPatientBtn: document.getElementById('printPatientBtn'),
        // Analyses actions
        analysesSearch: document.getElementById('analysesSearch'),
        analysesFilter: document.getElementById('analysesFilter'),
        refreshAnalysesBtn: document.getElementById('refreshAnalysesBtn'),
        // Epicrisis actions
        downloadEpicrisisBtn: document.getElementById('downloadEpicrisisBtn'),
        printEpicrisisBtn: document.getElementById('printEpicrisisBtn'),
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
        
        // Initialize dashboard data
        initDashboard();
        
        // Initialize header stats
        updateHeaderStats();
        
        // Check for notifications
        checkNotifications();
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
        
        // Notifications
        if (elements.notificationsBtn) {
            elements.notificationsBtn.addEventListener('click', toggleNotifications);
        }
        
        // User menu
        if (elements.userMenuBtn) {
            elements.userMenuBtn.addEventListener('click', toggleUserMenu);
        }
        
        // Click outside to close dropdowns
        document.addEventListener('click', function(e) {
            if (!elements.userDropdown.contains(e.target) && e.target !== elements.userMenuBtn) {
                elements.userDropdown.style.display = 'none';
            }
        });
        
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
        
        if (elements.refreshAnalysesBtn) {
            elements.refreshAnalysesBtn.addEventListener('click', refreshAnalyses);
        }
        
        // Export and print buttons
        if (elements.exportPatientBtn) {
            elements.exportPatientBtn.addEventListener('click', exportPatientData);
        }
        
        if (elements.printPatientBtn) {
            elements.printPatientBtn.addEventListener('click', printPatientData);
        }
        
        if (elements.downloadEpicrisisBtn) {
            elements.downloadEpicrisisBtn.addEventListener('click', downloadEpicrisis);
        }
        
        if (elements.printEpicrisisBtn) {
            elements.printEpicrisisBtn.addEventListener('click', printEpicrisis);
        }
        
        // Report tab buttons
        if (elements.copyReportBtn) {
            elements.copyReportBtn.addEventListener('click', copyReportMarkdown);
        }
    }
    
    function switchTab(tabId) {
        // Update active nav item
        elements.navItems.forEach(nav => nav.classList.remove('active'));
        const activeNavItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
        if (activeNavItem) activeNavItem.classList.add('active');
        
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
        const tabsToShow = ['patient', 'analyses', 'epicrisis', 'report', 'dashboard'];
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
        
        const dashboardTab = document.getElementById('dashboard-tab');
        if (dashboardTab) {
            dashboardTab.hidden = false;
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
        if (elements.checkoutIdsList) elements.checkoutIdsList.innerHTML = '';
        
        // Clear analyses with null checks
        if (elements.analysesGrid) elements.analysesGrid.innerHTML = '';
        if (elements.noAnalyses) elements.noAnalyses.style.display = 'none';
        
        // Clear epicrisis with null checks
        if (elements.epicrisisContent) elements.epicrisisContent.innerHTML = '';
        if (elements.epicrisisDate) elements.epicrisisDate.style.display = 'none';
        if (elements.epicrisisTitle) elements.epicrisisTitle.textContent = 'DIAGNOSTIC';
        if (elements.epicrisisFooter) elements.epicrisisFooter.style.display = 'none';
        if (elements.epicrisisSection) elements.epicrisisSection.style.display = 'none';
        
        // Clear report with null checks
        if (elements.reportPatientId) elements.reportPatientId.textContent = 'N/A';
        if (elements.reportPatientName) elements.reportPatientName.textContent = 'N/A';
        if (elements.reportPatientAge) elements.reportPatientAge.textContent = 'N/A';
        if (elements.reportPatientGender) elements.reportPatientGender.textContent = 'N/A';
        if (elements.reportRecentAnalyses) elements.reportRecentAnalyses.innerHTML = `
            <div class="no-data">
                <i class="fas fa-file-medical fa-2x" aria-hidden="true"></i>
                <p>No recent analyses available</p>
            </div>
        `;
        
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
    
    function initDashboard() {
        // Initialize Chart.js for patient overview
        if (elements.patientChart) {
            const ctx = elements.patientChart.getContext('2d');
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Active', 'Discharged', 'Critical'],
                    datasets: [{
                        data: [75, 20, 5],
                        backgroundColor: ['#36a2eb', '#ff6384', '#ffce56'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        }
        
        // Initialize recent activity
        if (elements.activityList) {
            const activities = [
                { icon: 'fa-user-injured', text: 'New patient admitted', time: '2 minutes ago' },
                { icon: 'fa-file-medical', text: 'Lab report uploaded', time: '15 minutes ago' },
                { icon: 'fa-x-ray', text: 'Imaging study completed', time: '1 hour ago' },
                { icon: 'fa-prescription', text: 'Prescription updated', time: '3 hours ago' }
            ];
            
            activities.forEach(activity => {
                const div = document.createElement('div');
                div.className = 'activity-item';
                div.innerHTML = `
                    <i class="fas ${activity.icon}"></i>
                    <div>
                        <div>${activity.text}</div>
                        <small>${activity.time}</small>
                    </div>
                `;
                elements.activityList.appendChild(div);
            });
        }
        
        // Initialize alerts
        if (elements.alertsList) {
            const alerts = [
                { type: 'warning', icon: 'fa-exclamation-triangle', text: 'Patient vitals unstable', time: 'Just now' },
                { type: 'info', icon: 'fa-info-circle', text: 'Lab results pending', time: '10 minutes ago' },
                { type: 'danger', icon: 'fa-heartbeat', text: 'Critical blood pressure', time: '30 minutes ago' }
            ];
            
            alerts.forEach(alert => {
                const div = document.createElement('div');
                div.className = `alert-item ${alert.type}`;
                div.innerHTML = `
                    <i class="fas ${alert.icon}"></i>
                    <div>
                        <div>${alert.text}</div>
                        <small>${alert.time}</small>
                    </div>
                `;
                elements.alertsList.appendChild(div);
            });
        }
        
        // Initialize upcoming
        if (elements.upcomingList) {
            const upcoming = [
                { icon: 'fa-calendar-check', text: 'Follow-up appointment', time: 'Tomorrow, 10:00 AM' },
                { icon: 'fa-syringe', text: 'Blood test scheduled', time: 'Friday, 2:00 PM' },
                { icon: 'fa-x-ray', text: 'MRI scan', time: 'Next Monday, 9:00 AM' }
            ];
            
            upcoming.forEach(item => {
                const div = document.createElement('div');
                div.className = 'upcoming-item';
                div.innerHTML = `
                    <i class="fas ${item.icon}"></i>
                    <div>
                        <div>${item.text}</div>
                        <small>${item.time}</small>
                    </div>
                `;
                elements.upcomingList.appendChild(div);
            });
        }
    }
    
    function updateHeaderStats() {
        // These would normally come from an API
        const stats = {
            activePatients: 1234,
            reportsToday: 156,
            criticalCases: 12
        };
        
        if (elements.activePatientsCount) {
            elements.activePatientsCount.textContent = stats.activePatients;
        }
        if (elements.reportsToday) {
            elements.reportsToday.textContent = stats.reportsToday;
        }
        if (elements.criticalCases) {
            elements.criticalCases.textContent = stats.criticalCases;
        }
    }
    
    function checkNotifications() {
        // Simulate checking for notifications
        const notifications = 3;
        if (elements.notificationBadge) {
            if (notifications > 0) {
                elements.notificationBadge.textContent = notifications;
                elements.notificationBadge.style.display = 'inline-block';
            }
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
    
    function toggleNotifications() {
        showToast('Notifications feature coming soon', 'info');
    }
    
    function toggleUserMenu() {
        const isHidden = elements.userDropdown.style.display === 'none' || !elements.userDropdown.style.display;
        elements.userDropdown.style.display = isHidden ? 'block' : 'none';
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
    
    function refreshAnalyses() {
        showToast('Refreshing analyses...', 'info');
        // This would normally reload the analyses data
    }
    
    function exportPatientData() {
        showToast('Exporting patient data...', 'success');
        // This would normally trigger a download
    }
    
    function printPatientData() {
        window.print();
    }
    
    function downloadEpicrisis() {
        showToast('Downloading epicrisis PDF...', 'success');
        // This would normally trigger a PDF download
    }
    
    function printEpicrisis() {
        const printContent = elements.epicrisisContent.innerHTML;
        const printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <html>
                <head>
                    <title>Epicrisis - ${elements.epicrisisTitle.textContent}</title>
                    <style>
                        body { font-family: Arial, sans-serif; }
                        h1 { color: #333; }
                        .content { margin: 20px; }
                    </style>
                </head>
                <body>
                    <h1>${elements.epicrisisTitle.textContent}</h1>
                    <div class="content">${printContent}</div>
                </body>
            </html>
        `);
        printWindow.document.close();
        printWindow.print();
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
            const dischargeStr  = ep.dischargeDate  ? ep.dischargeDate.toLocaleDateString('ro-RO')  : 'unknown';
            const admissionStr  = ep.admissionDate  ? ep.admissionDate.toLocaleDateString('ro-RO')  : 'unknown';
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
       
    // Make functions available globally
    window.viewFullEpicrisis = function(checkoutId) {
        // This would open a modal or navigate to a detailed view
        log('Viewing full epicrisis for checkout:', checkoutId);
        showToast('Full epicrisis view feature coming soon', 'info');
    };
    
    window.printEpicrisis = function(checkoutId) {
        // This would print the epicrisis
        log('Printing epicrisis for checkout:', checkoutId);
        showToast('Print epicrisis feature coming soon', 'info');
    };
    
    async function fetchAndDisplayReportContent(serviceRequestId, analysisItem) {
        try {
            const reportResponse = await fetch(`/fhir/DiagnosticReport/${serviceRequestId}`);
            
            if (!reportResponse.ok) {
                log(`Report not found for service request ${serviceRequestId}`);
                return;
            }
            
            const reportData = await reportResponse.json();
            const reportContainer = analysisItem.querySelector('.analysis-report');
            
            if (!reportContainer) return;
            
            // Clear loading state
            reportContainer.innerHTML = '';
            
            // Display report content
            if (reportData.conclusion) {
                const htmlContent = marked.parse(reportData.conclusion);
                reportContainer.innerHTML = htmlContent;
            } else if (reportData.presentedForm && reportData.presentedForm.length > 0) {
                reportData.presentedForm.forEach(form => {
                    if (form.contentType === 'text/plain' && form.data) {
                        const pre = document.createElement('pre');
                        pre.textContent = form.data;
                        reportContainer.appendChild(pre);
                    } else if (form.contentType === 'text/markdown' && form.data) {
                        const html = marked.parse(form.data);
                        const div = document.createElement('div');
                        div.innerHTML = html;
                        reportContainer.appendChild(div);
                    } else if (form.contentType === 'text/html' && form.data) {
                        const div = document.createElement('div');
                        div.innerHTML = form.data;
                        reportContainer.appendChild(div);
                    }
                });
            } else {
                reportContainer.innerHTML = '<p>No report content available</p>';
            }
            
        } catch (err) {
            console.error('Error fetching report content:', err);
            const reportContainer = analysisItem.querySelector('.analysis-report');
            if (reportContainer) {
                reportContainer.innerHTML = '<p>Error loading report</p>';
            }
        }
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
    
    // Utility function for API error handling
    function handleApiError(response, context = 'API request') {
        const errorMessages = {
            401: 'Authentication required. Please refresh the page and enter your credentials.',
            403: 'Access forbidden. You do not have permission to access this resource.',
            404: 'Resource not found. Please check the patient identifier and try again.',
            500: 'Server error. Please try again later.',
            503: 'Service unavailable. Please try again later.'
        };
        
        const defaultMessage = `${context} failed. Please try again.`;
        const message = errorMessages[response.status] || defaultMessage;
        
        showToast(message, 'error');
        return message;
    }
    
    // Utility function for network error handling
    function handleNetworkError(error, context = 'Network request') {
        console.error(`${context} failed:`, error);
        
        const message = 'Network error. Please check your connection and try again.';
        showToast(message, 'error');
        return message;
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
        
        // Display checkout IDs list
        const checkoutIds = extractCheckoutIds(patientData);
        log('Checkout IDs:', checkoutIds);
        displayCheckoutIds(checkoutIds);
        
        // Initialize sections but keep them hidden until data is loaded
        elements.epicrisisSection.style.display = 'none';
        elements.analysesGrid.innerHTML = '';
        elements.noAnalyses.style.display = 'none';
        
        // Update report tab data
        updateReportTabData(patientData, stats, analysesData);
        
        // Update dashboard stats if available
        updateDashboardStats(stats, analysesData);
        
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
        
        try {
            const date = new Date(birthDate);
            return date.toLocaleDateString('en-GB', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });
        } catch (err) {
            return birthDate;
        }
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
    
    // Enhanced checkout IDs display
    function displayCheckoutIds(checkoutIds) {
        log('Displaying checkout IDs:', checkoutIds);
        if (!checkoutIds || checkoutIds.length === 0) {
            elements.checkoutIdsList.innerHTML = '';
            log('No checkout IDs to display');
            return;
        }
        
        const idsHtml = checkoutIds.map(id => 
            `<span class="checkout-id">${id}</span>`
        ).join(', ');
        
        elements.checkoutIdsList.innerHTML = `
            <strong><i class="fas fa-sign-out-alt"></i> Checkout IDs:</strong> 
            ${idsHtml}
        `;
        log('Checkout IDs displayed');
    }
    
    // Update report tab data
    function updateReportTabData(patientData, stats, analysesData) {
        log('Updating report tab data');
        
        // Update patient summary with null checks
        if (elements.reportPatientId) {
            elements.reportPatientId.textContent = patientData.id || 'N/A';
        }
        if (elements.reportPatientName) {
            elements.reportPatientName.textContent = formatPatientName(patientData.name);
        }
        if (elements.reportPatientAge) {
            elements.reportPatientAge.textContent = calculateAge(patientData.birthDate);
        }
        if (elements.reportPatientGender) {
            elements.reportPatientGender.textContent = formatGender(patientData.gender);
        }
        
        log('Report tab data updated');
    }
    
    // Enhanced dashboard stats update
    function updateDashboardStats(stats, analysesData) {
        log('Updating dashboard stats - Stats:', stats, 'Analyses data:', analysesData);
        
        // Update header stats if available
        if (elements.activePatientsCount) {
            elements.activePatientsCount.textContent = stats.encounters;
            log('Active patients count updated to:', stats.encounters);
        }
        
        // Update reports count when analyses load
        const reportsCountElement = document.getElementById('reportsCount');
        if (reportsCountElement) {
            const reportsCount = analysesData.resourceType === "Bundle" && analysesData.entry 
                ? analysesData.entry.length : 0;
            reportsCountElement.textContent = `${reportsCount}`;
            log('Reports count badge updated to:', reportsCount);
        } else {
            log('Reports count element not found');
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
            p.innerHTML = `<strong><i class="fas fa-calendar"></i> Started:</strong> ${studyData.started}`;
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
    
    // Utility functions for better code organization
    const Utils = {
        // Debounce function for search input
        debounce: (func, wait) => {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        // Format date helper
        formatDate: (dateString) => {
            if (!dateString) return 'Unknown';
            const date = new Date(dateString);
            return date.toLocaleDateString('en-GB');
        },
        
        // Format time helper
        formatTime: (dateString) => {
            if (!dateString) return '';
            const date = new Date(dateString);
            return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        },
        
        // Check if element exists
        elementExists: (selector) => {
            return document.querySelector(selector) !== null;
        }
    };
    
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
                        showToast(`Report data loaded for service request ${serviceRequest.id}`, 'success');
                        
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
                        showToast(`Error loading report data for service request ${serviceRequest.id}`, 'error');
                    }
                } catch (err) {
                    console.error('Error fetching report data:', err);
                    showToast(`Error loading report data for service request ${serviceRequest.id}`, 'error');
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
    
    // Helper function to create analysis card
    function createAnalysisCard(serviceRequest, analysisType, analysisText) {
        log('Creating analysis card for:', serviceRequest, analysisType, analysisText);
        
        // Always use template
        const cardTemplate = document.getElementById('analysis-card-template');
        if (!cardTemplate) {
            console.error('Analysis card template not found');
            return document.createElement('div'); // fallback
        }
        
        const analysisCard = cardTemplate.content.cloneNode(true);
        const article = analysisCard.querySelector('article');
        if (!article) {
            console.error('Failed to clone analysis card template');
            return document.createElement('div'); // fallback
        }
        
        article.className = `analysis-card ${analysisType}`;
        
        // Populate template elements
        log('Populating template elements');
        const typeText = article.querySelector('.type-text');
        if (typeText) typeText.textContent = analysisText;
        
        const header = article.querySelector('h4');
        if (header) header.innerHTML = `<i class="fas fa-file-medical"></i> <span class="report-id">#${serviceRequest.id}</span>`;
        
        // Set exam date with enhanced formatting
        const examDateElement = article.querySelector('.exam-date');
        if (examDateElement) {
            if (serviceRequest.authoredOn) {
                const formattedDate = formatDateWithTime(serviceRequest.authoredOn);
                examDateElement.innerHTML = `<i class="fas fa-calendar"></i> ${formattedDate}`;
            } else {
                examDateElement.innerHTML = '<i class="fas fa-calendar"></i> Date: Unknown';
            }
        }
        
        // Add status indicator
        const statusElement = article.querySelector('.status');
        if (statusElement) {
            statusElement.textContent = serviceRequest.status || 'Unknown';
        }
        
        // Add medic name if available
        const medicNameElement = article.querySelector('.medic-name');
        if (medicNameElement && serviceRequest.requester) {
            medicNameElement.textContent = serviceRequest.requester.display || 'Unknown';
        }
        
        log('Analysis card created successfully');
        return article;
    }
    
    // Enhanced date formatting function
    function formatDateWithTime(dateString) {
        if (!dateString) return 'Unknown';
        
        try {
            const date = new Date(dateString);
            const dateOptions = { 
                day: '2-digit', 
                month: '2-digit', 
                year: 'numeric' 
            };
            const timeOptions = { 
                hour: '2-digit', 
                minute: '2-digit' 
            };
            
            const formattedDate = date.toLocaleDateString('en-GB', dateOptions);
            const formattedTime = date.toLocaleTimeString('en-GB', timeOptions);
            
            return `${formattedDate} at ${formattedTime}`;
        } catch (err) {
            return dateString;
        }
    }
    
    // Enhanced report preview formatting
    function formatReportPreview(reportText, maxLength = 200) {
        if (!reportText) return 'No preview available';
        
        // Remove markdown formatting for preview
        let cleanText = reportText.replace(/[#*_\[\]`]/g, '');
        
        // Truncate if too long
        if (cleanText.length > maxLength) {
            cleanText = cleanText.substring(0, maxLength) + '...';
        }
        
        return cleanText;
    }
    
    // Enhanced medic name formatting
    function formatMedicName(medicData) {
        if (!medicData) return 'Unknown';
        
        if (typeof medicData === 'string') {
            return medicData;
        }
        
        if (medicData.display) {
            return medicData.display;
        }
        
        if (medicData.name) {
            return formatPatientName([medicData.name]);
        }
        
        return 'Unknown';
    }
    
    // Function to load and display epicrisis progressively
    async function loadAndDisplayEpicrisis(patientData) {
        // Extract all checkout IDs from patient extensions
        const checkoutIds = extractCheckoutIds(patientData);
        
        if (checkoutIds.length === 0) {
            elements.epicrisisSection.style.display = 'none';
            return;
        }
        
        // Try to fetch epicrisis data for each checkout ID until we find a valid one
        for (const checkoutId of checkoutIds) {
            const success = await loadEpicrisisForCheckout(checkoutId);
            if (success) {
                showToast(`Valid epicrisis data loaded for checkout ${checkoutId}`, 'success');
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
            showToast(`Loading epicrisis data for checkout ${checkoutId}...`, 'success');
            const encounterData = await fetchEncounterDataForCheckout(checkoutId);
            
            if (!encounterData) {
                showToast(`Not found epicrisis data for checkout ${checkoutId}`, 'error');
                return false;
            }
            const epicrisisText = extractEpicrisisText(encounterData);
            
            if (!epicrisisText) {
                showToast(`No epicrisis data found for checkout ${checkoutId}`, 'error');
                return false;
            }
            
            await displayEpicrisisData(encounterData, epicrisisText);
            return true;
            
        } catch (err) {
            console.error('Error fetching encounter data:', err);
            showToast(`Error loading epicrisis data for checkout ${checkoutId}`, 'error');
            return false;
        }
    }
    
    // Helper function to extract epicrisis text from encounter data
    function extractEpicrisisText(encounterData) {
        if (!encounterData.note || !Array.isArray(encounterData.note)) return '';
        
        // Concatenate all note texts
        return encounterData.note.map(note => note.text || '').join('\n\n');
    }
    
    // Helper function to display epicrisis data
    async function displayEpicrisisData(encounterData, epicrisisText) {
        try {
            const htmlContent = marked.parse(epicrisisText);
            elements.epicrisisContent.innerHTML = htmlContent;
            
            // Set diagnosis title if available - prioritize discharge diagnosis
            const diagnosisText = extractDiagnosisText(encounterData);
            elements.epicrisisTitle.innerHTML = `<i class="fas fa-diagnoses"></i> Epicrisis: ${diagnosisText}`;
            
            // Display date if available
            displayEpicrisisDate(encounterData);
            
            // Extract medic name from attender (ATND) participant and display in footer
            displayMedicInfo(encounterData);
            
            elements.epicrisisSection.style.display = 'block';
            
            // Force UI update to display the epicrisis immediately
            await new Promise(resolve => setTimeout(resolve, 0));
            
        } catch (err) {
            console.error('Error converting epicrisis markdown:', err);
            elements.epicrisisContent.textContent = epicrisisText;
            elements.epicrisisDate.style.display = 'none';
            elements.epicrisisFooter.style.display = 'none';
        }
    }
    
    // Helper function to extract diagnosis text
    function extractDiagnosisText(encounterData) {
        if (!encounterData.diagnosis || encounterData.diagnosis.length === 0) {
            return 'DIAGNOSTIC';
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
        
        return 'DIAGNOSTIC';
    }
    
    // Helper function to display epicrisis date
    function displayEpicrisisDate(encounterData) {
        if (encounterData.period && encounterData.period.end) {
            const dateTime = new Date(encounterData.period.end);
            const formattedDate = dateTime.toLocaleDateString('en-GB');
            const formattedTime = dateTime.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
            elements.epicrisisDate.innerHTML = `<i class="fas fa-calendar"></i> Date: ${formattedDate} ${formattedTime}`;
            elements.epicrisisDate.style.display = 'block';
        } else {
            elements.epicrisisDate.style.display = 'none';
        }
    }
    
    // Helper function to display medic information
    function displayMedicInfo(encounterData) {
        if (!encounterData.participant || encounterData.participant.length === 0) {
            elements.epicrisisFooter.style.display = 'none';
            return;
        }
        
        // Look for participant with ATND type
        const attenderParticipant = encounterData.participant.find(p => 
            p.type && p.type.some(t => 
                t.coding && t.coding.some(c => c.code === "ATND")
            )
        );
        
        if (attenderParticipant && attenderParticipant.individual && attenderParticipant.individual.display) {
            elements.epicrisisFooter.innerHTML = `<i class="fas fa-user-md"></i> Medic: ${attenderParticipant.individual.display}`;
            elements.epicrisisFooter.style.display = 'block';
        } else {
            elements.epicrisisFooter.style.display = 'none';
        }
    }
});
