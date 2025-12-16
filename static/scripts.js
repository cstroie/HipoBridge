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
        // Dashboard elements
        dashboardTab: document.getElementById('dashboard-tab'),
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
    
    // Form submission handler
    elements.form.addEventListener('submit', handleFormSubmit);
    
    async function handleFormSubmit(e) {
        e.preventDefault();
        
        const cnp = elements.cnpInput.value.trim();
        
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
            const searchResult = await performPatientSearch(cnp);
            
            if (!searchResult.success) {
                showToast(searchResult.message, 'error');
                return;
            }
            
            const { patientData, patientCode } = searchResult;
            
            // Get analyses using FHIR API with better error handling
            const analysesResult = await fetchAnalysesData(patientCode);
            
            if (!analysesResult.success) {
                showToast(analysesResult.message, 'error');
                return;
            }
            
            const analysesData = analysesResult.data;
            
            // Display patient data first
            await displayPatientData(patientData, analysesData);
            
            // Load and display reports first, then epicrisis
            await loadAndDisplayReports(analysesData, patientData);
            await loadAndDisplayEpicrisis(patientData);
            
            // Switch to patient profile tab with enhanced navigation
            switchToPatientTab();
            
            showToast('Analysis loading complete', 'success');
            
        } catch (err) {
            console.error('Error:', err);
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
        // Update navigation
        elements.navItems.forEach(nav => nav.classList.remove('active'));
        const patientNavItem = document.querySelector('.nav-item[data-tab="patient"]');
        if (patientNavItem) {
            patientNavItem.classList.add('active');
        }
        
        // Show relevant tabs
        const tabsToShow = ['patient', 'analyses', 'epicrisis', 'dashboard'];
        tabsToShow.forEach(tabName => {
            const tabElement = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
            if (tabElement) {
                tabElement.style.display = 'block';
            }
        });
        
        // Update tab content display
        elements.tabContents.forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        
        const patientTab = document.getElementById('patient-tab');
        if (patientTab) {
            patientTab.classList.add('active');
            patientTab.style.display = 'block';
        }
    }
    
    function showLoading() {
        elements.loadingOverlay.style.display = 'flex';
        elements.analyzeBtn.disabled = true;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
    }
    
    function hideLoading() {
        elements.loadingOverlay.style.display = 'none';
        elements.analyzeBtn.disabled = false;
        elements.analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }
    
    function clearResults() {
        // Clear patient data
        elements.patientId.textContent = '';
        elements.patientName.textContent = '';
        elements.patientCnp.textContent = '';
        elements.patientGender.textContent = '';
        elements.patientBirthDate.textContent = '';
        elements.patientPhone.textContent = '';
        elements.patientEmail.textContent = '';
        elements.presentationsCount.textContent = '0';
        elements.checkinsCount.textContent = '0';
        elements.checkoutsCount.textContent = '0';
        elements.checkoutIdsList.innerHTML = '';
        
        // Clear analyses
        elements.analysesGrid.innerHTML = '';
        elements.noAnalyses.style.display = 'none';
        
        // Clear epicrisis
        elements.epicrisisContent.innerHTML = '';
        elements.epicrisisDate.style.display = 'none';
        elements.epicrisisTitle.textContent = 'DIAGNOSTIC';
        elements.epicrisisFooter.style.display = 'none';
        elements.epicrisisSection.style.display = 'none';
        
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
            const type = card.className.match(/radio|ct|irm|eco|lac|lii|rads/)?.[0] || '';
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
    
    function loadRecentSearches() {
        const recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        if (elements.recentSearchesList) {
            elements.recentSearchesList.innerHTML = '';
            recentSearches.forEach(search => {
                const div = document.createElement('div');
                div.className = 'recent-item';
                div.innerHTML = `
                    <span>${search}</span>
                    <button class="btn-icon btn-small" onclick="searchFromRecent('${search}')">
                        <i class="fas fa-search"></i>
                    </button>
                `;
                elements.recentSearchesList.appendChild(div);
            });
        }
    }
    
    function addToRecentSearches(searchTerm) {
        let recentSearches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        // Remove if already exists
        recentSearches = recentSearches.filter(search => search !== searchTerm);
        // Add to beginning
        recentSearches.unshift(searchTerm);
        // Keep only last 5
        recentSearches = recentSearches.slice(0, 5);
        localStorage.setItem('recentSearches', JSON.stringify(recentSearches));
        loadRecentSearches();
    }
    
    // Make function available globally
    window.searchFromRecent = function(searchTerm) {
        elements.cnpInput.value = searchTerm;
        elements.form.dispatchEvent(new Event('submit'));
    };
    
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
    
    async function convertMarkdownToHtml(markdownText) {
        try {
            const response = await fetch('/fhir/md2html', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text: markdownText })
            });
            
            if (response.status === 401) {
                showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                throw new Error('Authentication required');
            }
            
            const data = await response.json();
            if (data.status === 'success') {
                return data.html;
            } else {
                throw new Error('Markdown conversion failed');
            }
        } catch (err) {
            console.error('Error converting markdown to HTML:', err);
            return markdownText; // Return original text if conversion fails
        }
    }

    function displayPatientData(patientData, analysesData, epicrisisData = null) {
        // Enhanced patient information display with better formatting
        displayPatientBasicInfo(patientData);
        
        // Extract and display medical statistics
        const stats = extractMedicalStats(patientData);
        displayMedicalStats(stats);
        
        // Display checkout IDs list
        const checkoutIds = extractCheckoutIds(patientData);
        displayCheckoutIds(checkoutIds);
        
        // Initialize sections but keep them hidden until data is loaded
        elements.epicrisisSection.style.display = 'none';
        elements.analysesGrid.innerHTML = '';
        elements.noAnalyses.style.display = 'none';
        
        // Update dashboard stats if available
        updateDashboardStats(stats, analysesData);
    }
    
    // Enhanced patient basic info display
    function displayPatientBasicInfo(patientData) {
        // Patient ID
        elements.patientId.textContent = patientData.id || 'N/A';
        
        // Patient Name with enhanced formatting
        const name = formatPatientName(patientData.name);
        elements.patientName.innerHTML = `<i class="fas fa-user"></i> ${name}`;
        
        // Add age badge
        const age = calculateAge(patientData.birthDate);
        const ageElement = document.createElement('span');
        ageElement.className = 'badge badge-info';
        ageElement.textContent = `Age: ${age}`;
        elements.patientName.appendChild(ageElement);
        
        // CNP with validation
        const cnp = extractCNP(patientData.identifier);
        elements.patientCnp.textContent = cnp || 'N/A';
        
        // Gender with icons
        const gender = formatGender(patientData.gender);
        elements.patientGender.textContent = gender;
        
        // Birth date with formatting
        elements.patientBirthDate.textContent = formatBirthDate(patientData.birthDate);
        
        // Contact information
        const contactInfo = extractContactInfo(patientData.telecom);
        elements.patientPhone.textContent = contactInfo.phone || 'N/A';
        elements.patientEmail.textContent = contactInfo.email || 'N/A';
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
                ext.url && ext.url.includes('encounter-ids')
            );
            const admissionExt = patientData.extension.find(ext => 
                ext.url && ext.url.includes('admission-ids')
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
        elements.presentationsCount.textContent = stats.encounters;
        elements.checkinsCount.textContent = stats.admissions;
        elements.checkoutsCount.textContent = stats.discharges;
        
        // Add reports count badge
        const reportsCountElement = document.createElement('span');
        reportsCountElement.className = 'badge badge-secondary';
        reportsCountElement.textContent = `Reports: 0`; // Will be updated when reports load
        if (elements.presentationsCount && elements.presentationsCount.parentElement) {
            elements.presentationsCount.parentElement.appendChild(reportsCountElement);
        }
    }
    
    // Enhanced checkout IDs display
    function displayCheckoutIds(checkoutIds) {
        if (!checkoutIds || checkoutIds.length === 0) {
            elements.checkoutIdsList.innerHTML = '';
            return;
        }
        
        const idsHtml = checkoutIds.map(id => 
            `<span class="checkout-id">${id}</span>`
        ).join(', ');
        
        elements.checkoutIdsList.innerHTML = `
            <strong><i class="fas fa-sign-out-alt"></i> Checkout IDs:</strong> 
            ${idsHtml}
        `;
    }
    
    // Enhanced dashboard stats update
    function updateDashboardStats(stats, analysesData) {
        // Update header stats if available
        if (elements.activePatientsCount) {
            elements.activePatientsCount.textContent = stats.encounters;
        }
        
        // Update reports count when analyses load
        if (elements.presentationsCount && elements.presentationsCount.parentElement) {
            const reportsBadge = elements.presentationsCount.parentElement.querySelector('.badge-secondary');
            if (reportsBadge) {
                const reportsCount = analysesData.resourceType === "Bundle" && analysesData.entry 
                    ? analysesData.entry.length : 0;
                reportsBadge.textContent = `Reports: ${reportsCount}`;
            }
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
        // Check if we have a FHIR Bundle of ServiceRequests
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            elements.noAnalyses.style.display = 'none';
            
            // Filter for imaging analyses only
            const imagingTypes = ['radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'];
            const imagingEntries = analysesData.entry.filter(entry => {
                const serviceRequest = entry.resource;
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                return imagingTypes.includes(analysisType);
            });
            
            if (imagingEntries.length === 0) {
                elements.noAnalyses.style.display = 'block';
                return;
            }
            
            // Process each service request
            for (const entry of imagingEntries) {
                const serviceRequest = entry.resource;
                
                // Extract type and display text from service request code
                const analysisType = serviceRequest.code?.coding?.[0]?.code || 'unknown';
                const analysisText = serviceRequest.code?.coding?.[0]?.display || 'analysis';
                
                // Create analysis card using template
                const analysisCard = createAnalysisCard(serviceRequest, analysisType, analysisText);
                
                // For imaging analyses, fetch and display report content
                if (['radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'].includes(analysisType)) {
                    try {
                        // Fetch report data using FHIR API - now using the service request ID directly
                        const reportResponse = await fetch(`/fhir/DiagnosticReport/${serviceRequest.id}`);
                        
                        if (reportResponse.ok) {
                            const reportData = await reportResponse.json();
                            showToast(`Report data loaded for service request ${serviceRequest.id}`, 'success');
                            
                            // Add performer and interpreter to footer if available
                            const reportFooter = analysisCard.querySelector('.report-footer');
                            if (reportData.resultsInterpreter && reportData.resultsInterpreter.length > 0) {
                                // Add interpreter if available
                                if (reportData.resultsInterpreter && reportData.resultsInterpreter.length > 0) {
                                    const p = document.createElement('p');
                                    p.innerHTML = `<strong><i class="fas fa-user-md"></i> Medic:</strong> ${reportData.resultsInterpreter[0].display || ''}`;
                                    reportFooter.appendChild(p);
                                }
                            }
                            
                            // Add report content to the card - now using presentedForm or conclusion
                            const reportPreview = analysisCard.querySelector('.report-preview');
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
                                        try {
                                            const htmlResult = await convertMarkdownToHtml(form.data);
                                            const div = document.createElement('div');
                                            div.innerHTML = htmlResult;
                                            reportPreview.appendChild(div);
                                        } catch (err) {
                                            console.error('Error converting markdown:', err);
                                            const pre = document.createElement('pre');
                                            pre.textContent = form.data;
                                            reportPreview.appendChild(pre);
                                        }
                                    } else if (form.contentType === 'text/html' && form.data) {
                                        const div = document.createElement('div');
                                        div.innerHTML = form.data;
                                        reportPreview.appendChild(div);
                                    }
                                }
                            } else if (reportData.conclusion) {
                                try {
                                    const htmlResult = await convertMarkdownToHtml(reportData.conclusion);
                                    const div = document.createElement('div');
                                    div.innerHTML = htmlResult;
                                    reportPreview.appendChild(div);
                                } catch (err) {
                                    console.error('Error converting report markdown:', err);
                                    const p = document.createElement('p');
                                    p.textContent = reportData.conclusion;
                                    reportPreview.appendChild(p);
                                }
                            }
                            
                            // Add link to ImagingStudy if available
                            const imagingStudyLink = analysisCard.querySelector('.imaging-study-link');
                            if (reportData.imagingStudy) {
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
                            showToast(`Error loading report data for service request ${serviceRequest.id}`, 'error');
                        }
                    } catch (err) {
                        console.error('Error fetching report data:', err);
                        showToast(`Error loading report data for service request ${serviceRequest.id}`, 'error');
                    }
                }
                
                elements.analysesGrid.appendChild(analysisCard);
                
                // Force UI update to display the report immediately
                await new Promise(resolve => setTimeout(resolve, 0));
            }
        } else {
            elements.noAnalyses.style.display = 'block';
        }
    }
    
    // Helper function to create analysis card
    function createAnalysisCard(serviceRequest, analysisType, analysisText) {
        const cardTemplate = document.getElementById('analysis-card-template');
        const analysisCard = cardTemplate.content.cloneNode(true).querySelector('article');
        analysisCard.className = `analysis-card ${analysisType}`;
        
        // Set card header with enhanced formatting
        const header = analysisCard.querySelector('h4');
        header.innerHTML = `
            <i class="fas fa-file-medical"></i> 
            ${analysisText} 
            <span class="report-id">#${serviceRequest.id}</span>
        `;
        
        // Set exam date with enhanced formatting
        const examDateElement = analysisCard.querySelector('.exam-date');
        if (serviceRequest.authoredOn) {
            const formattedDate = formatDateWithTime(serviceRequest.authoredOn);
            examDateElement.innerHTML = `<i class="fas fa-calendar"></i> ${formattedDate}`;
        } else {
            examDateElement.innerHTML = '<i class="fas fa-calendar"></i> Date: Unknown';
        }
        
        // Add type badge
        const typeBadge = analysisCard.querySelector('.type-text');
        if (typeBadge) {
            typeBadge.textContent = analysisText;
        }
        
        // Add status indicator
        const statusElement = analysisCard.querySelector('.status');
        if (statusElement) {
            statusElement.textContent = serviceRequest.status || 'Unknown';
        }
        
        return analysisCard;
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
            const encounterResponse = await fetch(`/fhir/Encounter/${checkoutId}`);
            
            if (!encounterResponse.ok) {
                showToast(`Not found epicrisis data for checkout ${checkoutId}`, 'error');
                return false;
            }
            
            const encounterData = await encounterResponse.json();
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
            const htmlContent = await convertMarkdownToHtml(epicrisisText);
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
