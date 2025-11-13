
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('cnpForm');
    const cnpInput = document.getElementById('cnpInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const errorDiv = document.getElementById('error');
    const results = document.getElementById('results');
    
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
        
        // Show loading state
        showLoading();
        hideError();
        results.style.display = 'none';
        
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
                        showError('Invalid CNP. Please check the number and try again.');
                        return;
                    }
                } catch (err) {
                    console.error('Error validating CNP:', err);
                    showError('Error validating CNP. Please try again.');
                    return;
                }
    
                showToast('Valid CNP detected. Retrieving patient information...', 'success');
            } else if (isPartialCNPFormat) {
                showToast('Searching for patient with partial CNP...', 'success');
            } else {
                // For patient name/code searches
                showToast('Searching for patient by name or code...', 'success');
            }
            
            // Search for patient using FHIR API
            showToast('Searching patient database...', 'success');
            const searchResponse = await fetch(`/fhir/Patient?q=${encodeURIComponent(cnp)}`);
            
            if (!searchResponse.ok) {
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
                showError('No patient found with this search term.');
                return;
            }
            
            if (!patientCode || !patientData) {
                console.error('Failed to retrieve patient data:', { patientCode, patientData });
                showError('Failed to retrieve patient data.');
                return;
            }
            
            showToast('Patient information retrieved successfully. Loading analyses...', 'success');
            
            // Get analyses using FHIR API
            showToast('Loading patient analyses...', 'success');
            const analysesResponse = await fetch(`/fhir/Observation?patient=${patientCode}`);
            
            if (!analysesResponse.ok) {
                showToast(`Error loading analyses: HTTP ${analysesResponse.status}`, 'error');
                throw new Error(`HTTP error! status: ${analysesResponse.status}`);
            }
            
            const analysesData = await analysesResponse.json();
            showToast('Patient analyses loaded successfully', 'success');
            
            // Get the most recent checkout epicrisis using FHIR API
            let epicrisisData = null;
            if (patientData.discharges && patientData.discharges.length > 0) {
                showToast('Loading epicrisis data...', 'success');
                // Get the most recent discharge (first in the list)
                const dischargeId = patientData.discharges[0];
                try {
                    showToast(`Loading epicrisis data for discharge ${dischargeId}...`, 'success');
                    const dischargeResponse = await fetch(`/fhir/Encounter?identifier=${dischargeId}`);
                    
                    if (dischargeResponse.ok) {
                        const dischargeData = await dischargeResponse.json();
                        epicrisisData = {
                            epicrisis: dischargeData.text ? dischargeData.text.div : '',
                            date: dischargeData.period ? dischargeData.period.start : '',
                            discharge_id: dischargeId
                        };
                        showToast(`Epicrisis data loaded for discharge ${dischargeId}`, 'success');
                    } else {
                        showToast(`Error loading epicrisis data for discharge ${dischargeId}: HTTP ${dischargeResponse.status}`, 'error');
                    }
                } catch (err) {
                    console.error('Error fetching discharge data:', err);
                    showToast(`Error loading epicrisis data for discharge ${dischargeId}`, 'error');
                }
            }
            
            // Display all data
            await displayPatientData(patientData, analysesData, epicrisisData);
            showToast('Analysis complete!', 'success');
            
        } catch (err) {
            console.error('Error:', err);
            showError('An error occurred while analyzing the patient data. Please try again.');
        } finally {
            hideLoading();
        }
    });
    
    function showLoading() {
        analyzeBtn.disabled = true;
    }
    
    function hideLoading() {
        analyzeBtn.disabled = false;
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
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // Add toast to container
        toastContainer.appendChild(toast);
        
        // Remove toast after animation completes
        setTimeout(() => {
            toast.remove();
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
        document.getElementById('patientName').textContent = (patientData.name && patientData.name[0]) 
            ? `${patientData.name[0].family || ''} ${patientData.name[0].given ? patientData.name[0].given.join(' ') : ''}` 
            : 'N/A';
        document.getElementById('patientCode').textContent = patientData.id || 'N/A';
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
        
        // Extract address information
        if (patientData.address && patientData.address[0]) {
            document.getElementById('patientAddress').textContent = patientData.address[0].text || 'N/A';
        } else {
            document.getElementById('patientAddress').textContent = 'N/A';
        }
        
        // Extract encounter/admission/discharge counts from extensions
        let encounterCount = 0, admissionCount = 0, dischargeCount = 0;
        if (patientData.extension) {
            const encounterExt = patientData.extension.find(ext => ext.url && ext.url.includes('encounter-ids'));
            const admissionExt = patientData.extension.find(ext => ext.url && ext.url.includes('admission-ids'));
            const dischargeExt = patientData.extension.find(ext => ext.url && ext.url.includes('discharge-ids'));
            
            encounterCount = encounterExt ? encounterExt.valueString.split(',').filter(id => id).length : 0;
            admissionCount = admissionExt ? admissionExt.valueString.split(',').filter(id => id).length : 0;
            dischargeCount = dischargeExt ? dischargeExt.valueString.split(',').filter(id => id).length : 0;
        }
        
        document.getElementById('presentationsCount').textContent = encounterCount;
        document.getElementById('checkinsCount').textContent = admissionCount;
        document.getElementById('checkoutsCount').textContent = dischargeCount;
        
        // Display epicrisis if available
        const epicrisisSection = document.getElementById('epicrisisSection');
        if (epicrisisData && epicrisisData.epicrisis) {
            // Convert markdown to HTML for epicrisis
            try {
                const htmlContent = await convertMarkdownToHtml(epicrisisData.epicrisis);
                document.getElementById('epicrisisContent').innerHTML = htmlContent;
                
                // Display date if available
                const dateElement = document.getElementById('epicrisisDate');
                if (epicrisisData.date) {
                    dateElement.textContent = `Date: ${epicrisisData.date}`;
                    dateElement.style.display = 'block';
                } else {
                    dateElement.style.display = 'none';
                }
            } catch (err) {
                console.error('Error converting epicrisis markdown:', err);
                document.getElementById('epicrisisContent').textContent = epicrisisData.epicrisis;
                document.getElementById('epicrisisDate').style.display = 'none';
            }
            epicrisisSection.style.display = 'block';
        } else {
            epicrisisSection.style.display = 'none';
        }
        
        // Display analyses
        const analysesGrid = document.getElementById('analysesGrid');
        const noAnalyses = document.getElementById('noAnalyses');
        
        // Check if we have a FHIR Bundle of Observations
        if (analysesData.resourceType === "Bundle" && analysesData.entry && analysesData.entry.length > 0) {
            noAnalyses.style.display = 'none';
            analysesGrid.innerHTML = '';
            
            // Process each observation - only display imaging analyses
            for (const entry of analysesData.entry) {
                const observation = entry.resource;
                
                // Extract type from observation code
                let analysisType = 'unknown';
                if (observation.code && observation.code.coding && observation.code.coding.length > 0) {
                    analysisType = observation.code.coding[0].code || 'unknown';
                }
                // Extract display text from observation display
                let analysisText = 'analysis';
                if (observation.code && observation.code.coding && observation.code.coding.length > 0) {
                    analysisText = observation.code.coding[0].display || 'analysis';
                }
                
                // Display analyses with imaging types 'radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'
                if (!['radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'].includes(analysisType)) {
                    continue;
                }
                
                const analysisCard = document.createElement('article');
                analysisCard.className = `analysis-card ${analysisType}`;
                
                // Start building the card content
                let cardContent = `
                    <header>
                        <h4>${analysisText} report #${observation.id}</h4>
                    </header>
                    <main>
                `;
                
                // For imaging analyses, fetch and display report content
                if (['radio', 'ct', 'irm', 'eco', 'lac', 'lii', 'rads'].includes(analysisType)) {
                    try {
                        // Fetch report data using FHIR API - now using the observation ID directly
                        showToast(`Loading report data for observation ${observation.id}...`, 'success');
                        const reportResponse = await fetch(`/fhir/DiagnosticReport/${observation.id}`);
                        
                        if (reportResponse.ok) {
                            const reportData = await reportResponse.json();
                            showToast(`Report data loaded for observation ${observation.id}`, 'success');
                            
                            // Add report metadata (date/time and performer) if available
                            if (reportData.effectiveDateTime || (reportData.performer && reportData.performer.length > 0)) {
                                cardContent += `<div class="report-meta">`;
                                if (reportData.effectiveDateTime) {
                                    cardContent += `<p><strong>Date/Time:</strong> ${reportData.effectiveDateTime}</p>`;
                                }
                                if (reportData.performer && reportData.performer.length > 0) {
                                    cardContent += `<p><strong>Performer:</strong> ${reportData.performer[0].display || ''}</p>`;
                                }
                                // Add interpreter if available
                                if (reportData.resultsInterpreter && reportData.resultsInterpreter.length > 0) {
                                    cardContent += `<p><strong>Interpreter:</strong> ${reportData.resultsInterpreter[0].display || ''}</p>`;
                                }
                                cardContent += `</div>`;
                            }
                            
                            // Add report content to the card - now using presentedForm or conclusion
                            cardContent += `<div class="report-preview">`;
                            if (reportData.presentedForm && reportData.presentedForm.length > 0) {
                                // Use the first presentedForm entry
                                const form = reportData.presentedForm[0];
                                if (form.contentType === 'text/plain' && form.data) {
                                    cardContent += `<pre>${form.data}</pre>`;
                                } else if (form.contentType === 'text/markdown' && form.data) {
                                    const htmlResult = await convertMarkdownToHtml(reportData.conclusion);
                                    cardContent += `<div>${htmlResult}</div>`;
                                } else if (form.contentType === 'text/html' && form.data) {
                                    // Decode base64 if needed
                                    try {
                                        const decoded = atob(form.data);
                                        cardContent += `<div>${decoded}</div>`;
                                    } catch (e) {
                                        cardContent += `<div>${form.data}</div>`;
                                    }
                                }
                            } else if (reportData.conclusion) {
                                try {
                                    const htmlResult = await convertMarkdownToHtml(reportData.conclusion);
                                    cardContent += `<div>${htmlResult}</div>`;
                                } catch (err) {
                                    console.error('Error converting report markdown:', err);
                                    cardContent += `<p>${reportData.conclusion}</p>`;
                                }
                            }
                            cardContent += `</div>`;
                            
                            // Add link to ImagingStudy if available
                            if (reportData.imagingStudy) {
                                const studyId = reportData.imagingStudy.reference.split('/')[1];
                                cardContent += `<div class="imaging-study-link">
                                    <a href="#" onclick="viewImagingStudy('${studyId}', '${observation.id}'); return false;">
                                        View Imaging Study #${studyId}
                                    </a>
                                </div>`;
                            }
                        } else {
                            showToast(`Error loading report data for observation ${observation.id}: HTTP ${reportResponse.status}`, 'error');
                        }
                    } catch (err) {
                        console.error('Error fetching report data:', err);
                        showToast(`Error loading report data for observation ${observation.id}`, 'error');
                    }
                }
                
                cardContent += `
                    </main>
                `;
                
                analysisCard.innerHTML = cardContent;
                analysesGrid.appendChild(analysisCard);
            }
            
            // Check if we actually added any cards
            if (analysesGrid.children.length === 0) {
                noAnalyses.style.display = 'block';
            }
        } else {
            noAnalyses.style.display = 'block';
            analysesGrid.innerHTML = '';
        }
        
        // Show results
        results.style.display = 'block';
    }
    
    // Function to view imaging study
    async function viewImagingStudy(studyId, reportId) {
        try {
            // Fetch imaging study data using FHIR API
            showToast(`Loading imaging study ${studyId}...`, 'success');
            const studyResponse = await fetch(`/fhir/ImagingStudy/${studyId}`);
            
            if (studyResponse.ok) {
                const studyData = await studyResponse.json();
                displayImagingStudyModal(studyData, studyId, reportId);
                showToast(`Imaging study ${studyId} loaded successfully`, 'success');
            } else {
                console.error('Error fetching imaging study data');
                showToast(`Error loading imaging study ${studyId}: HTTP ${studyResponse.status}`, 'error');
            }
        } catch (err) {
            console.error('Error fetching imaging study:', err);
            showToast(`Error loading imaging study ${studyId}`, 'error');
        }
    }
    
    // Function to display imaging study in a modal
    function displayImagingStudyModal(studyData, studyId, reportId) {
        // Use PicoCSS modal
        const modal = document.createElement('dialog');
        modal.id = 'imagingStudyModal';
        modal.className = 'modal';
        
        let content = `
            <article>
                <header>
                    <h2>Imaging Study #${studyId}</h2>
                    <button class="close" aria-label="Close" rel="prev"></button>
                </header>
                <main>
        `;
        
        // Study metadata
        content += `<div class="study-section">`;
        content += `<h3>Study Information</h3>`;
        
        if (studyData.started) {
            content += `<p><strong>Started:</strong> ${studyData.started}</p>`;
        }
        
        if (studyData.modality) {
            content += `<p><strong>Modality:</strong> ${studyData.modality.display || studyData.modality.code || 'N/A'}</p>`;
        }
        
        if (studyData.description) {
            content += `<p><strong>Description:</strong> ${studyData.description}</p>`;
        }
        
        // Performer information
        if (studyData.performer && studyData.performer.length > 0) {
            content += `<p><strong>Performer:</strong> ${studyData.performer[0].actor?.display || 'N/A'}</p>`;
        }
        
        // Referrer information
        if (studyData.referrer) {
            content += `<p><strong>Referrer:</strong> ${studyData.referrer.display || 'N/A'}</p>`;
        }
        
        // Reason information
        if (studyData.reason && studyData.reason.length > 0) {
            content += `<p><strong>Reason:</strong> ${studyData.reason[0].text || 'N/A'}</p>`;
        }
        
        // Note information
        if (studyData.note && studyData.note.length > 0) {
            content += `<p><strong>Note:</strong> ${studyData.note[0].text || 'N/A'}</p>`;
        }
        
        content += `</div>`;
        
        // Series information
        if (studyData.series && studyData.series.length > 0) {
            content += `<section class="study-section">`;
            content += `<h3>Series</h3>`;
            content += `<ul>`;
            
            studyData.series.forEach((series, index) => {
                content += `<li><strong>Series ${series.number || index + 1}:</strong> ${series.description || 'N/A'}`;
                if (series.modality) {
                    content += ` (Modality: ${series.modality.display || series.modality.code || 'N/A'})`;
                }
                content += `</li>`;
            });
            
            content += `</ul>`;
            content += `</section>`;
        }
        
        // Link back to report
        content += `<section class="study-section">`;
        content += `<p><a href="#" onclick="closeImagingStudyModal(); return false;">Back to Report #${reportId}</a></p>`;
        content += `</section>`;
        
        content += `
                </main>
                <footer>
                    <button class="secondary" data-close-modal>Close</button>
                </footer>
            </article>
        `;
        
        modal.innerHTML = content;
        document.body.appendChild(modal);
        
        // Add event listeners for closing the modal
        const closeButtons = modal.querySelectorAll('[data-close-modal], .close');
        closeButtons.forEach(button => {
            button.addEventListener('click', () => {
                modal.remove();
            });
        });
        
        // Show modal
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
});
