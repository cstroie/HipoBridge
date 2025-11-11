
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
                    patient_name: searchData.name && searchData.name[0] ? 
                        `${searchData.name[0].given.join(' ')} ${searchData.name[0].family}` : 'N/A',
                    patient_code: searchData.id,
                    patient_id: searchData.identifier ? 
                        searchData.identifier.find(id => id.system === "http://hospital-system/cnp")?.value : '',
                    presentations: [],
                    checkins: [],
                    checkouts: []
                };
                
                // Extract checkin/checkout IDs from extensions if available
                if (searchData.extension) {
                    const checkinExt = searchData.extension.find(ext => 
                        ext.url === "http://hospital-system/StructureDefinition/checkin-ids");
                    const checkoutExt = searchData.extension.find(ext => 
                        ext.url === "http://hospital-system/StructureDefinition/checkout-ids");
                    
                    if (checkinExt) {
                        patientData.checkins = checkinExt.valueString.split(',');
                    }
                    if (checkoutExt) {
                        patientData.checkouts = checkoutExt.valueString.split(',');
                    }
                }
            } else if (searchData.resourceType === "Bundle" && searchData.entry && searchData.entry.length > 0) {
                // Multiple patients in a bundle
                const firstPatient = searchData.entry[0].resource;
                patientCode = firstPatient.id;
                
                // Get full patient data using FHIR API
                const patientResponse = await fetch(`/fhir/Patient/${patientCode}`);
                if (patientResponse.ok) {
                    const patientResult = await patientResponse.json();
                    patientData = {
                        patient_name: patientResult.name && patientResult.name[0] ? 
                            `${patientResult.name[0].given.join(' ')} ${patientResult.name[0].family}` : 'N/A',
                        patient_code: patientResult.id,
                        patient_id: patientResult.identifier ? 
                            patientResult.identifier.find(id => id.system === "http://hospital-system/cnp")?.value : '',
                        presentations: [],
                        checkins: [],
                        checkouts: []
                    };
                    
                    // Extract checkin/checkout IDs from extensions if available
                    if (patientResult.extension) {
                        const checkinExt = patientResult.extension.find(ext => 
                            ext.url === "http://hospital-system/StructureDefinition/checkin-ids");
                        const checkoutExt = patientResult.extension.find(ext => 
                            ext.url === "http://hospital-system/StructureDefinition/checkout-ids");
                        
                        if (checkinExt) {
                            patientData.checkins = checkinExt.valueString.split(',');
                        }
                        if (checkoutExt) {
                            patientData.checkouts = checkoutExt.valueString.split(',');
                        }
                    }
                } else {
                    // Fallback if we can't get detailed patient data
                    patientData = {
                        patient_name: firstPatient.name && firstPatient.name[0] ? 
                            `${firstPatient.name[0].given.join(' ')} ${firstPatient.name[0].family}` : 'N/A',
                        patient_code: firstPatient.id,
                        patient_id: firstPatient.identifier ? 
                            firstPatient.identifier.find(id => id.system === "http://hospital-system/cnp")?.value : '',
                        presentations: [],
                        checkins: [],
                        checkouts: []
                    };
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
            const analysesData = await analysesResponse.json();
            
            if (analysesData.status !== 'success') {
                console.error('Failed to retrieve patient analyses:', analysesData);
                showError('Failed to retrieve patient analyses.');
                return;
            }
            
            // Get the most recent checkout epicrisis using FHIR API
            let epicrisisData = null;
            if (patientData.checkouts && patientData.checkouts.length > 0) {
                showToast('Loading epicrisis data...', 'success');
                // Get the most recent checkout (first in the list)
                const checkoutId = patientData.checkouts[0];
                try {
                    const checkoutResponse = await fetch(`/fhir/Encounter?identifier=${checkoutId}`);
                    const checkoutData = await checkoutResponse.json();
                    
                    if (checkoutData.status === 'success') {
                        epicrisisData = {
                            epicrisis: checkoutData.epicrisis || '',
                            date: checkoutData.sample_datetime || '',
                            checkout_id: checkoutId
                        };
                    }
                } catch (err) {
                    console.error('Error fetching checkout data:', err);
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
            toastContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(toastContainer);
        }
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            padding: 12px 20px;
            border-radius: 4px;
            color: white;
            background-color: ${type === 'success' ? '#4caf50' : '#f44336'};
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            animation: slideIn 0.3s, fadeOut 0.5s 2.5s forwards;
            max-width: 300px;
        `;
        
        // Add CSS for animations
        if (!document.getElementById('toast-styles')) {
            const style = document.createElement('style');
            style.id = 'toast-styles';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes fadeOut {
                    from { opacity: 1; }
                    to { opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }
        
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
        document.getElementById('patientId').textContent = patientData.patient_id || 'N/A';
        document.getElementById('patientName').textContent = patientData.patient_name || 'N/A';
        document.getElementById('patientCode').textContent = patientData.patient_code || 'N/A';
        document.getElementById('patientCnp').textContent = patientData.patient_id || 'N/A';
        document.getElementById('presentationsCount').textContent = (patientData.presentations || []).length;
        document.getElementById('checkinsCount').textContent = (patientData.checkins || []).length;
        document.getElementById('checkoutsCount').textContent = (patientData.checkouts || []).length;
        
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
        
        if (analysesData.analyses && analysesData.analyses.length > 0) {
            noAnalyses.style.display = 'none';
            analysesGrid.innerHTML = '';
            
            // Process each analysis - only display imaging analyses
            for (const analysis of analysesData.analyses) {
                // Only display analyses with types 'radio', 'ct', 'irm', or 'eco'
                if (!analysis.type || !['radio', 'ct', 'irm', 'eco'].includes(analysis.type)) {
                    continue;
                }
                
                const analysisCard = document.createElement('article');
                analysisCard.className = `analysis-card ${analysis.type || 'unknown'}`;
                
                // Start building the card content
                let cardContent = `
                    <header>
                        <h4>Analysis #${analysis.report_id} ${analysis.type || ''}</h4>
                    </header>
                    <main>
                `;
                
                // For imaging analyses, fetch and display report content
                if (analysis.type && ['radio', 'ct', 'irm', 'eco'].includes(analysis.type)) {
                    try {
                        // Fetch report data using FHIR API
                        const reportResponse = await fetch(`/fhir/DiagnosticReport?identifier=${analysis.report_id}`);
                        const reportData = await reportResponse.json();
                        
                        if (reportData.status === 'success' && reportData.reports && reportData.reports.length > 0) {
                            // Add report metadata (date/time and examiner) if available
                            if (reportData.sample_datetime || reportData.examiner) {
                                cardContent += `<div class="report-meta">`;
                                if (reportData.sample_datetime) {
                                    cardContent += `<p><strong>Date/Time:</strong> ${reportData.sample_datetime}</p>`;
                                }
                                if (reportData.examiner) {
                                    cardContent += `<p><strong>Examiner:</strong> ${reportData.examiner}</p>`;
                                }
                                cardContent += `</div>`;
                            }
                            
                            // Add report content to the card
                            cardContent += `<div class="report-preview">`;
                            for (const report of reportData.reports) {
                                cardContent += `<p><strong>${report.investigation || 'Investigation'}:</strong></p>`;
                                if (report.result) {
                                    try {
                                        const htmlResult = await convertMarkdownToHtml(report.result);
                                        cardContent += `<div>${htmlResult}</div>`;
                                    } catch (err) {
                                        console.error('Error converting report markdown:', err);
                                        cardContent += `<p>${report.result}</p>`;
                                    }
                                }
                            }
                            cardContent += `</div>`;
                        }
                    } catch (err) {
                        console.error('Error fetching report data:', err);
                    }
                }
                
                // Add the footer with the view report button
                cardContent += `
                    </main>
                `;
                
                analysisCard.innerHTML = cardContent;
                analysesGrid.appendChild(analysisCard);
            }
        } else {
            noAnalyses.style.display = 'block';
            analysesGrid.innerHTML = '';
        }
        
        // Show results
        results.style.display = 'block';
    }
    
    function displayReportModal(reportData, reportId, reportType) {
        // Use PicoCSS modal
        const modal = document.createElement('dialog');
        modal.id = 'reportModal';
        modal.className = 'modal';
        
        let content = `
            <article>
                <header>
                    <h2>${reportType.toUpperCase()} Report #${reportId}</h2>
                    <button class="close" aria-label="Close" rel="prev"></button>
                </header>
                <main>
        `;
        
        // Patient information
        content += `<div class="report-section">`;
        content += `<h3>`;
        content += `${reportData.patient_name}`;
        if (reportData.gender) {
            content += `, ${reportData.gender}`;
        }
        if (reportData.age) {
            content += `, ${reportData.age}`;
        }
        content += `</h3>`;
        
        if (reportData.patient_id) {
            content += `<p><strong>CNP:</strong> ${reportData.patient_id}</p>`;
        }
        if (reportData.patient_code) {
            content += `<p><strong>Patient Code:</strong> ${reportData.patient_code}</p>`;
        }
        if (reportData.sample_datetime) {
            content += `<p><strong>Date/Time:</strong> ${reportData.sample_datetime}</p>`;
        }
        
        content += `</div>`;
        
        // Report results
        if (reportData.reports && reportData.reports.length > 0) {
            content += `<section class="report-section">`;
            content += `<h3>Results</h3>`;
            
            reportData.reports.forEach((report, index) => {
                content += `<p><strong>${index + 1}: ${report.investigation || 'N/A'}</strong></p>`;
                content += `<pre style="white-space: pre-wrap; background: var(--muted-background-color); padding: 0.75rem; border-radius: var(--border-radius);">${report.result || 'No result data'}</pre>`;
            });
            
            content += `</section>`;
        } else if (reportData.result) {
            content += `<section class="report-section">`;
            content += `<h3>Result</h3>`;
            content += `<pre style="white-space: pre-wrap; background: var(--muted-background-color); padding: 0.75rem; border-radius: var(--border-radius);">${reportData.result}</pre>`;
            content += `</section>`;
        }
        
        // Examiner information
        if (reportData.examiner) {
            content += `<section class="report-section">`;
            content += `<p><strong>Examiner:</strong> ${reportData.examiner}</p>`;
            content += `</section>`;
        }
        
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
});
