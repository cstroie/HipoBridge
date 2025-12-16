document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const form = document.getElementById('cnpForm');
    const cnpInput = document.getElementById('cnpInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const errorDiv = document.getElementById('error');
    const backToSearchBtn = document.getElementById('backToSearch');
    
    // Tab navigation
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    
    // Hide all tab contents except search
    tabContents.forEach(tab => {
        if (!tab.classList.contains('active')) {
            tab.style.display = 'none';
        }
    });
    
    // Tab navigation handler
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Update active nav item
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');
            
            // Show corresponding tab content
            const tabId = this.getAttribute('data-tab');
            tabContents.forEach(tab => {
                tab.classList.remove('active');
                tab.style.display = 'none';
            });
            
            const targetTab = document.getElementById(`${tabId}-tab`);
            if (targetTab) {
                targetTab.classList.add('active');
                targetTab.style.display = 'block';
            }
        });
    });
    
    // Back to search button handler
    if (backToSearchBtn) {
        backToSearchBtn.addEventListener('click', function() {
            // Reset form
            form.reset();
            
            // Switch to search tab
            navItems.forEach(nav => nav.classList.remove('active'));
            document.querySelector('.nav-item[data-tab="search"]').classList.add('active');
            
            tabContents.forEach(tab => {
                tab.classList.remove('active');
                tab.style.display = 'none';
            });
            
            const searchTab = document.getElementById('search-tab');
            if (searchTab) {
                searchTab.classList.add('active');
                searchTab.style.display = 'block';
            }
            
            // Clear results
            clearResults();
        });
    }
    
    // Form submission handler
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const cnp = cnpInput.value.trim();
        
        // Validate input - allow CNP (13 digits), partial CNP (digits followed by *), or patient name
        if (!cnp) {
            showError('Please enter a valid patient identifier (CNP, partial CNP, patient code, or patient name)');
            return;
        }
        
        // Check if it's a CNP format (13 digits) or partial CNP (digits followed by *)
        const isCNPFormat = /^\d{13}$/.test(cnp);
        const isPartialCNPFormat = /^\d+\*$/.test(cnp);
            
        // Clear previous results
        clearResults();
        
        // Show loading state
        showLoading();
        hideError();
            
        // Notify user of search start
        showToast('Starting patient search...', 'success');
            
        try {
            // Determine search type and notify user
            if (isCNPFormat) {
                showToast('Validating CNP...', 'success');
                // Validate CNP using server-side FHIR API
                try {
                    const cnpResponse = await fetch(`/fhir/ValueSet/cnp?id=${cnp}`);
                    const cnpData = await cnpResponse.json();
            
                    if (!cnpData.valid) {
                        showToast('CNP is not valid, but proceeding with search...', 'error');
                    } else {
                        showToast('Valid CNP, retrieving patient information...', 'success');
                    }
                } catch (err) {
                    console.error('Error validating CNP:', err);
                    showToast('Error validating CNP, but proceeding with search...', 'error');
                }
            } else if (isPartialCNPFormat) {
                showToast('Searching for patient with partial CNP...', 'success');
            } else {
                // For patient name/code searches
                showToast('Searching for patient by name or code...', 'success');
            }
            
            // Search for patient using FHIR API
            const searchResponse = await fetch(`/fhir/Patient?q=${encodeURIComponent(cnp)}`);
            
            if (!searchResponse.ok) {
                if (searchResponse.status === 401) {
                    showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                }
                throw new Error(`HTTP error! status: ${searchResponse.status}`);
            }
            
            const searchData = await searchResponse.json();
            
            let patientCode = null;
            let patientData = null;
            
            // Check if it's a single patient (FHIR Patient resource) or multiple patients (FHIR Bundle)
            if (searchData.resourceType === "Patient") {
                // Single patient
                patientCode = searchData.id;
                patientData = {
                    id: searchData.id,
                    name: searchData.name,
                    identifier: searchData.identifier,
                    gender: searchData.gender,
                    birthDate: searchData.birthDate,
                    extension: searchData.extension,
                    telecom: searchData.telecom,
                    address: searchData.address
                };
            } else if (searchData.resourceType === "Bundle" && searchData.entry && searchData.entry.length > 0) {
                // Multiple patients in a bundle
                const firstPatient = searchData.entry[0].resource;
                patientCode = firstPatient.id;
                
                // Get full patient data using FHIR API
                const patientResponse = await fetch(`/fhir/Patient/${patientCode}`);
                if (patientResponse.ok) {
                    patientData = await patientResponse.json();
                } else {
                    // Fallback if we can't get detailed patient data
                    patientData = firstPatient;
                }
            } else {
                showToast('No patient found with this search term.', 'error');
                return;
            }
            
            if (!patientCode || !patientData) {
                console.error('Failed to retrieve patient data:', { patientCode, patientData });
                showToast('Failed to retrieve patient data.', 'error');
                return;
            }
            
            showToast('Patient information retrieved successfully', 'success');
            
            // Get analyses using FHIR API
            showToast('Loading diagnostic reports...', 'success');
            const analysesResponse = await fetch(`/fhir/ServiceRequest?patient=${patientCode}&full=yes`);
            
            if (!analysesResponse.ok) {
                if (analysesResponse.status === 401) {
                    showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                }
                showToast(`Error loading diagnostic reports`, 'error');
                throw new Error(`HTTP error! status: ${analysesResponse.status}`);
            }
            
            const analysesData = await analysesResponse.json();
            showToast('Patient diagnostic reports loaded successfully', 'success');
            
            // Get the most recent valid checkout epicrisis using FHIR API
            let epicrisisData = null;
            // Extract all checkout IDs from patient extensions
            let checkoutIds = [];
            if (patientData.extension) {
                const checkoutExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkout-ids'));
                if (checkoutExt && checkoutExt.valueString) {
                    checkoutIds = checkoutExt.valueString.split(',').filter(id => id.trim());
                }
            }
            
            // Try to fetch epicrisis data for each checkout ID until we find a valid one
            for (const checkoutId of checkoutIds) {
                try {
                    showToast(`Loading epicrisis data for checkout ${checkoutId}...`, 'success');
                    const checkoutResponse = await fetch(`/api/checkout/${checkoutId}`);
                    
                    if (checkoutResponse.ok) {
                        const checkoutData = await checkoutResponse.json();
                        // Check if this checkout has valid epicrisis data
                        // Handle both single resource and Bundle responses
                        let encounterData = checkoutData;
                        if (checkoutData.resourceType === "Bundle" && checkoutData.entry && checkoutData.entry.length > 0) {
                            encounterData = checkoutData.entry[0].resource;
                        }
                        
                        // Extract epicrisis from notes array
                        let epicrisisText = '';
                        if (encounterData.note && Array.isArray(encounterData.note)) {
                            // Concatenate all note texts
                            epicrisisText = encounterData.note.map(note => note.text || '').join('\n\n');
                        }
                            
                        // Extract checkout date and time if available
                        let checkoutDateTime = '';
                        if (encounterData.period && encounterData.period.start) {
                            checkoutDateTime = encounterData.period.start;
                        }
                        
                        if (epicrisisText) {
                            epicrisisData = {
                                epicrisis: epicrisisText,
                                date: encounterData.period ? encounterData.period.start : '',
                                checkout_id: checkoutId
                            };
                            showToast(`Valid epicrisis data loaded for checkout ${checkoutId}`, 'success');
                            break; // Found a valid epicrisis, stop searching
                        } else {
                            showToast(`No epicrisis data found for checkout ${checkoutId}`, 'error');
                        }
                    } else {
                        if (checkoutResponse.status === 401) {
                            showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                        }
                        showToast(`Not found epicrisis data for checkout ${checkoutId}`, 'error');
                    }
                } catch (err) {
                    console.error('Error fetching checkout data:', err);
                    showToast(`Error loading epicrisis data for checkout ${checkoutId}`, 'error');
                }
            }
            
            // Display patient data first
            await displayPatientData(patientData, analysesData, epicrisisData);
            
            // Load and display reports first, then epicrisis
            await loadAndDisplayReports(analysesData, patientData);
            await loadAndDisplayEpicrisis(patientData);
            
            // Switch to patient profile tab
            navItems.forEach(nav => nav.classList.remove('active'));
            document.querySelector('.nav-item[data-tab="patient"]').classList.add('active');
            document.querySelector('.nav-item[data-tab="analyses"]').style.display = 'block';
            document.querySelector('.nav-item[data-tab="epicrisis"]').style.display = 'block';
            
            tabContents.forEach(tab => {
                tab.classList.remove('active');
                tab.style.display = 'none';
            });
            
            document.getElementById('patient-tab').classList.add('active');
            document.getElementById('patient-tab').style.display = 'block';
            
            showToast('Analysis loading complete', 'success');
            
        } catch (err) {
            console.error('Error:', err);
            showToast('An error occurred while analyzing the patient data', 'error');
        } finally {
            hideLoading();
        }
    });
    
    function showLoading() {
        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
    }
    
    function hideLoading() {
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = '<i class="fas fa-search"></i> Search Patient';
    }
    
    function clearResults() {
        // Clear patient data
        document.getElementById('patientId').textContent = '';
        document.getElementById('patientName').textContent = '';
        document.getElementById('patientCnp').textContent = '';
        document.getElementById('patientGender').textContent = '';
        document.getElementById('patientBirthDate').textContent = '';
        document.getElementById('patientPhone').textContent = '';
        document.getElementById('patientEmail').textContent = '';
        document.getElementById('presentationsCount').textContent = '0';
        document.getElementById('checkinsCount').textContent = '0';
        document.getElementById('checkoutsCount').textContent = '0';
        document.getElementById('checkoutIdsList').innerHTML = '';
        
        // Clear analyses
        document.getElementById('analysesGrid').innerHTML = '';
        document.getElementById('noAnalyses').style.display = 'none';
        
        // Clear epicrisis
        document.getElementById('epicrisisContent').innerHTML = '';
        document.getElementById('epicrisisDate').style.display = 'none';
        document.getElementById('epicrisisTitle').textContent = 'DIAGNOSTIC';
        document.getElementById('epicrisisFooter').style.display = 'none';
        
        // Hide navigation tabs for patient data
        document.querySelector('.nav-item[data-tab="patient"]').style.display = 'none';
        document.querySelector('.nav-item[data-tab="analyses"]').style.display = 'none';
        document.querySelector('.nav-item[data-tab="epicrisis"]').style.display = 'none';
        
        // Clear any existing toasts
        const toastContainer = document.getElementById('toast-container');
        if (toastContainer) {
            toastContainer.innerHTML = '';
        }
    }
    
    function showError(message) {
        console.error('Application error:', message);
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        hideLoading();
    }
    
    function hideError() {
        errorDiv.style.display = 'none';
    }
    
    function showToast(message, type = 'success') {
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
        const icon = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle';
        toast.innerHTML = `<i class="fas ${icon}"></i> ${message}`;
        
        // Add toast to container
        toastContainer.appendChild(toast);
        
        // Remove toast after animation completes
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3000);
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

    async function displayPatientData(patientData, analysesData, epicrisisData = null) {
        // Display patient information
        document.getElementById('patientId').textContent = patientData.id || 'N/A';
        document.getElementById('patientName').innerHTML = `<i class="fas fa-user"></i> ${(patientData.name && patientData.name[0]) 
            ? `${patientData.name[0].family || ''} ${patientData.name[0].given ? patientData.name[0].given.join(' ') : ''}` 
            : 'N/A'}`;
        document.getElementById('patientCnp').textContent = patientData.identifier 
            ? patientData.identifier.find(id => id.system && id.system.includes('cnp'))?.value || 'N/A' 
            : 'N/A';
        document.getElementById('patientGender').textContent = patientData.gender || 'N/A';
        document.getElementById('patientBirthDate').textContent = patientData.birthDate || 'N/A';
        
        // Extract telecom information
        if (patientData.telecom) {
            const phone = patientData.telecom.find(t => t.system === 'phone');
            const email = patientData.telecom.find(t => t.system === 'email');
            document.getElementById('patientPhone').textContent = phone ? phone.value : 'N/A';
            document.getElementById('patientEmail').textContent = email ? email.value : 'N/A';
        } else {
            document.getElementById('patientPhone').textContent = 'N/A';
            document.getElementById('patientEmail').textContent = 'N/A';
        }
        
        // Extract encounter/admission/discharge counts and IDs from extensions
        let encounterCount = 0, admissionCount = 0, dischargeCount = 0;
        let checkoutIds = [];
        if (patientData.extension) {
            const encounterExt = patientData.extension.find(ext => ext.url && ext.url.includes('encounter-ids'));
            const admissionExt = patientData.extension.find(ext => ext.url && ext.url.includes('admission-ids'));
            const checkoutExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkout-ids'));
            
            encounterCount = encounterExt ? encounterExt.valueString.split(',').filter(id => id).length : 0;
            admissionCount = admissionExt ? admissionExt.valueString.split(',').filter(id => id).length : 0;
            
            if (checkoutExt) {
                checkoutIds = checkoutExt.valueString.split(',').filter(id => id);
                dischargeCount = checkoutIds.length;
            }
        }
        
        document.getElementById('presentationsCount').textContent = encounterCount;
        document.getElementById('checkinsCount').textContent = admissionCount;
        document.getElementById('checkoutsCount').textContent = dischargeCount;
        
        // Display checkout IDs list
        const checkoutIdsList = document.getElementById('checkoutIdsList');
        if (checkoutIds.length > 0) {
            checkoutIdsList.innerHTML = `<strong><i class="fas fa-sign-out-alt"></i> Checkout IDs:</strong> ${checkoutIds.join(', ')}`;
        } else {
            checkoutIdsList.innerHTML = '';
        }
        
        // Initialize sections but keep them hidden until data is loaded
        document.getElementById('epicrisisSection').style.display = 'none';
        document.getElementById('analysesGrid').innerHTML = '';
        document.getElementById('noAnalyses').style.display = 'none';
        
        // Force UI update to ensure patient card is displayed immediately
        await new Promise(resolve => setTimeout(resolve, 0));
    }
    
    // Function to view imaging study
    async function viewImagingStudy(studyId, reportId) {
        try {
            // Fetch imaging study data using FHIR API
            const studyResponse = await fetch(`/fhir/ImagingStudy/${studyId}`);
            
            if (studyResponse.ok) {
                const studyData = await studyResponse.json();
                displayImagingStudyModal(studyData, studyId, reportId);
                showToast(`Imaging study ${studyId} loaded successfully`, 'success');
            } else {
                if (studyResponse.status === 401) {
                    showToast('Authentication required. Please refresh the page and enter your credentials.', 'error');
                }
                console.error('Error fetching imaging study data');
                showToast(`Error loading imaging study ${studyId}`, 'error');
            }
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
        
        if (studyData.started) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-calendar"></i> Started:</strong> ${studyData.started}`;
            studyInfo.appendChild(p);
        }
        
        if (studyData.modality) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-stethoscope"></i> Modality:</strong> ${studyData.modality.display || studyData.modality.code || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        if (studyData.description) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-file-medical"></i> Description:</strong> ${studyData.description}`;
            studyInfo.appendChild(p);
        }
        
        // Performer information
        if (studyData.performer && studyData.performer.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-user-md"></i> Performer:</strong> ${studyData.performer[0].actor?.display || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Referrer information
        if (studyData.referrer) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-user-check"></i> Referrer:</strong> ${studyData.referrer.display || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Reason information
        if (studyData.reason && studyData.reason.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-question-circle"></i> Reason:</strong> ${studyData.reason[0].text || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Note information
        if (studyData.note && studyData.note.length > 0) {
            const p = document.createElement('p');
            p.innerHTML = `<strong><i class="fas fa-sticky-note"></i> Note:</strong> ${studyData.note[0].text || 'N/A'}`;
            studyInfo.appendChild(p);
        }
        
        // Series information
        const seriesList = modal.querySelector('.series-list');
        if (studyData.series && studyData.series.length > 0) {
            studyData.series.forEach((series, index) => {
                const li = document.createElement('li');
                li.innerHTML = `<strong><i class="fas fa-list-ol"></i> Series ${series.number || index + 1}:</strong> ${series.description || 'N/A'}`;
                if (series.modality) {
                    li.innerHTML += ` (Modality: ${series.modality.display || series.modality.code || 'N/A'})`;
                }
                seriesList.appendChild(li);
            });
        }
        
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
        const analysesGrid = document.getElementById('analysesGrid');
        const noAnalyses = document.getElementById('noAnalyses');
        
        // Check if we have a FHIR Bundle of ServiceRequests
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            noAnalyses.style.display = 'none';
            
            // Process each service request - only display imaging analyses
            for (const entry of analysesData.entry) {
                const serviceRequest = entry.resource;
                
                // Extract type from service request code
                let analysisType = 'unknown';
                if (serviceRequest.code && serviceRequest.code.coding && serviceRequest.code.coding.length > 0) {
                    analysisType = serviceRequest.code.coding[0].code || 'unknown';
                }
                // Extract display text from service request display
                let analysisText = 'analysis';
                if (serviceRequest.code && serviceRequest.code.coding && serviceRequest.code.coding.length > 0) {
                    analysisText = serviceRequest.code.coding[0].display || 'analysis';
                }
                
                // Display analyses with imaging types 'radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'
                if (!['radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'].includes(analysisType)) {
                    continue;
                }
                
                // Use template for analysis card
                const cardTemplate = document.getElementById('analysis-card-template');
                const analysisCard = cardTemplate.content.cloneNode(true).querySelector('article');
                analysisCard.className = `analysis-card ${analysisType}`;
                
                // Set card header
                analysisCard.querySelector('h4').innerHTML = `<i class="fas fa-file-medical"></i> ${analysisText} report #${serviceRequest.id}`;
                
                // Set exam date if available
                const examDateElement = analysisCard.querySelector('.exam-date');
                if (serviceRequest.authoredOn) {
                    // Parse ISO datetime and format it nicely
                    const dateTime = new Date(serviceRequest.authoredOn);
                    const formattedDate = dateTime.toLocaleDateString('en-GB');
                    const formattedTime = dateTime.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                    examDateElement.innerHTML = `<i class="fas fa-calendar"></i> Date: ${formattedDate} ${formattedTime}`;
                } else {
                    examDateElement.innerHTML = '<i class="fas fa-calendar"></i> Date: Unknown';
                }
                
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
                
                analysesGrid.appendChild(analysisCard);
                
                // Force UI update to display the report immediately
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            
            // Check if we actually added any cards
            if (analysesGrid.children.length === 0) {
                noAnalyses.style.display = 'block';
            }
        } else {
            noAnalyses.style.display = 'block';
        }
    }
    
    // Function to load and display epicrisis progressively
    async function loadAndDisplayEpicrisis(patientData) {
        // Extract all checkout IDs from patient extensions
        let checkoutIds = [];
        if (patientData.extension) {
            const checkoutExt = patientData.extension.find(ext => ext.url && ext.url.includes('checkout-ids'));
            if (checkoutExt && checkoutExt.valueString) {
                checkoutIds = checkoutExt.valueString.split(',').filter(id => id.trim());
            }
        }
        
        // Try to fetch epicrisis data for each checkout ID until we find a valid one
        for (const checkoutId of checkoutIds) {
            try {
                showToast(`Loading epicrisis data for checkout ${checkoutId}...`, 'success');
                const encounterResponse = await fetch(`/fhir/Encounter/${checkoutId}`);
                
                if (encounterResponse.ok) {
                    const encounterData = await encounterResponse.json();
                    
                    // Extract epicrisis from notes array
                    let epicrisisText = '';
                    if (encounterData.note && Array.isArray(encounterData.note)) {
                        // Concatenate all note texts
                        epicrisisText = encounterData.note.map(note => note.text || '').join('\n\n');
                    }
                    
                    if (epicrisisText) {
                        // Display epicrisis immediately
                        const epicrisisSection = document.getElementById('epicrisisSection');
                        const epicrisisTitle = document.getElementById('epicrisisTitle');
                        try {
                            const htmlContent = await convertMarkdownToHtml(epicrisisText);
                            document.getElementById('epicrisisContent').innerHTML = htmlContent;
                            
                            // Set diagnosis title if available - prioritize discharge diagnosis
                            let diagnosisText = 'DIAGNOSTIC';
                            if (encounterData.diagnosis && encounterData.diagnosis.length > 0) {
                                // Look for discharge diagnosis first (use code "DD")
                                const dischargeDiagnosis = encounterData.diagnosis.find(d => 
                                    d.use && d.use.coding && d.use.coding.some(c => c.code === "DD")
                                );
                                
                                if (dischargeDiagnosis && dischargeDiagnosis.condition && dischargeDiagnosis.condition.display) {
                                    diagnosisText = dischargeDiagnosis.condition.display;
                                } else {
                                    // Fallback to first diagnosis if no discharge diagnosis found
                                    const firstDiagnosis = encounterData.diagnosis[0];
                                    if (firstDiagnosis.condition && firstDiagnosis.condition.display) {
                                        diagnosisText = firstDiagnosis.condition.display;
                                    }
                                }
                            }
                            epicrisisTitle.innerHTML = `<i class="fas fa-diagnoses"></i> Epicrisis: ${diagnosisText}`;
                            
                            // Display date if available
                            const dateElement = document.getElementById('epicrisisDate');
                            if (encounterData.period && encounterData.period.end) {
                                // Parse ISO datetime and format it nicely
                                const dateTime = new Date(encounterData.period.end);
                                const formattedDate = dateTime.toLocaleDateString('en-GB');
                                const formattedTime = dateTime.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                                dateElement.innerHTML = `<i class="fas fa-calendar"></i> Date: ${formattedDate} ${formattedTime}`;
                                dateElement.style.display = 'block';
                            } else {
                                dateElement.style.display = 'none';
                            }
                            
                            // Extract medic name from attender (ATND) participant and display in footer
                            const footerElement = document.getElementById('epicrisisFooter');
                            if (encounterData.participant && encounterData.participant.length > 0) {
                                // Look for participant with ATND type
                                const attenderParticipant = encounterData.participant.find(p => 
                                    p.type && p.type.some(t => 
                                        t.coding && t.coding.some(c => c.code === "ATND")
                                    )
                                );
                                
                                if (attenderParticipant && attenderParticipant.individual && attenderParticipant.individual.display) {
                                    if (footerElement) {
                                        footerElement.innerHTML = `<i class="fas fa-user-md"></i> Medic: ${attenderParticipant.individual.display}`;
                                        footerElement.style.display = 'block';
                                    }
                                } else if (footerElement) {
                                    footerElement.style.display = 'none';
                                }
                            } else if (footerElement) {
                                footerElement.style.display = 'none';
                            }
                        } catch (err) {
                            console.error('Error converting epicrisis markdown:', err);
                            document.getElementById('epicrisisContent').textContent = epicrisisText;
                            document.getElementById('epicrisisDate').style.display = 'none';
                            // Hide footer on error
                            const footerElement = document.getElementById('epicrisisFooter');
                            if (footerElement) {
                                footerElement.style.display = 'none';
                            }
                        }
                        epicrisisSection.style.display = 'block';
                        
                        // Force UI update to display the epicrisis immediately
                        await new Promise(resolve => setTimeout(resolve, 0));
                        
                        showToast(`Valid epicrisis data loaded for checkout ${checkoutId}`, 'success');
                        break; // Found a valid epicrisis, stop searching
                    } else {
                        showToast(`No epicrisis data found for checkout ${checkoutId}`, 'error');
                    }
                } else {
                    showToast(`Not found epicrisis data for checkout ${checkoutId}`, 'error');
                }
            } catch (err) {
                console.error('Error fetching encounter data:', err);
                showToast(`Error loading epicrisis data for checkout ${checkoutId}`, 'error');
            }
        }
    }
});
