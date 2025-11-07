document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('cnpForm');
    const cnpInput = document.getElementById('cnpInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const loading = document.getElementById('loading');
    const errorDiv = document.getElementById('error');
    const successDiv = document.getElementById('success');
    const results = document.getElementById('results');
    
    // Form submission handler
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const cnp = cnpInput.value.trim();
        
        // Validate CNP format
        if (!cnp || cnp.length !== 13 || !/^\d+$/.test(cnp)) {
            showError('Please enter a valid 13-digit CNP');
            return;
        }
        
        // Show loading state
        showLoading();
        hideError();
        hideSuccess();
        results.style.display = 'none';
        
        try {
            // Validate CNP
            const cnpResponse = await fetch(`/api/cnp?id=${cnp}`);
            const cnpData = await cnpResponse.json();
            
            if (cnpData.status !== 'success' || !cnpData.valid) {
                showError('Invalid CNP. Please check the number and try again.');
                return;
            }
            
            showSuccess('Valid CNP detected. Retrieving patient information...');
            
            // Search for patient
            const searchResponse = await fetch(`/api/patients/search?q=${cnp}`);
            const searchData = await searchResponse.json();
            
            if (searchData.status !== 'success') {
                showError('Failed to retrieve patient information.');
                return;
            }
            
            let patientCode = null;
            let patientData = null;
            
            if (searchData.type === 'single_patient') {
                patientCode = searchData.data.patient_code;
                patientData = searchData.data;
            } else if (searchData.type === 'multiple_patients' && searchData.data.length > 0) {
                patientCode = searchData.data[0].patient_code;
                // Get full patient data
                const patientResponse = await fetch(`/api/patients?id=${patientCode}`);
                const patientResult = await patientResponse.json();
                if (patientResult.status === 'success') {
                    patientData = {
                        patient_name: searchData.data[0].patient_name,
                        patient_code: patientCode,
                        patient_id: cnp,
                        presentations: [],
                        checkins: patientResult.checkin_ids || [],
                        checkouts: patientResult.checkout_ids || []
                    };
                }
            } else {
                showError('No patient found with this CNP.');
                return;
            }
            
            if (!patientCode || !patientData) {
                showError('Failed to retrieve patient data.');
                return;
            }
            
            showSuccess('Patient information retrieved successfully. Loading analyses...');
            
            // Get analyses
            const analysesResponse = await fetch(`/api/analyses?id=${patientCode}`);
            const analysesData = await analysesResponse.json();
            
            if (analysesData.status !== 'success') {
                showError('Failed to retrieve patient analyses.');
                return;
            }
            
            // Display all data
            displayPatientData(patientData, analysesData);
            showSuccess('Analysis complete!');
            
        } catch (err) {
            console.error('Error:', err);
            showError('An error occurred while analyzing the patient data. Please try again.');
        } finally {
            hideLoading();
        }
    });
    
    function showLoading() {
        loading.style.display = 'block';
        analyzeBtn.disabled = true;
    }
    
    function hideLoading() {
        loading.style.display = 'none';
        analyzeBtn.disabled = false;
    }
    
    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        hideLoading();
    }
    
    function hideError() {
        errorDiv.style.display = 'none';
    }
    
    function showSuccess(message) {
        successDiv.textContent = message;
        successDiv.style.display = 'block';
    }
    
    function hideSuccess() {
        successDiv.style.display = 'none';
    }
    
    function displayPatientData(patientData, analysesData) {
        // Display patient information
        document.getElementById('patientId').textContent = patientData.patient_id || 'N/A';
        document.getElementById('patientName').textContent = patientData.patient_name || 'N/A';
        document.getElementById('patientCode').textContent = patientData.patient_code || 'N/A';
        document.getElementById('patientCnp').textContent = patientData.patient_id || 'N/A';
        document.getElementById('presentationsCount').textContent = (patientData.presentations || []).length;
        document.getElementById('checkinsCount').textContent = (patientData.checkins || []).length;
        document.getElementById('checkoutsCount').textContent = (patientData.checkouts || []).length;
        
        // Display analyses
        const analysesGrid = document.getElementById('analysesGrid');
        const noAnalyses = document.getElementById('noAnalyses');
        
        if (analysesData.analyses && analysesData.analyses.length > 0) {
            noAnalyses.style.display = 'none';
            analysesGrid.innerHTML = '';
            
            analysesData.analyses.forEach(analysis => {
                const analysisCard = document.createElement('article');
                analysisCard.className = `analysis-card ${analysis.type || 'unknown'}`;
                
                analysisCard.innerHTML = `
                    <div class="analysis-header">
                        <h4>Analysis #${analysis.report_id}</h4>
                        <span class="analysis-type">${analysis.type || 'Unknown'}</span>
                    </div>
                    <div class="analysis-content">
                        <p><strong>Type:</strong> ${analysis.type || 'Unknown'}</p>
                        <p><strong>Report ID:</strong> ${analysis.report_id}</p>
                        ${analysis.type && ['radio', 'ct', 'irm', 'eco'].includes(analysis.type) ? 
                            `<button class="view-report-btn secondary" data-id="${analysis.report_id}" data-type="${analysis.type}">View Report</button>` : 
                            ''}
                    </div>
                `;
                
                analysesGrid.appendChild(analysisCard);
            });
            
            // Add event listeners to view report buttons
            document.querySelectorAll('.view-report-btn').forEach(button => {
                button.addEventListener('click', async function() {
                    const reportId = this.getAttribute('data-id');
                    const reportType = this.getAttribute('data-type');
                    
                    // Show loading state
                    showLoading();
                    hideError();
                    hideSuccess();
                    
                    try {
                        // Fetch report data
                        const reportResponse = await fetch(`/api/reports?id=${reportId}`);
                        const reportData = await reportResponse.json();
                        
                        if (reportData.status !== 'success') {
                            showError(`Failed to retrieve ${reportType} report #${reportId}.`);
                            return;
                        }
                        
                        // Display report in a modal
                        displayReportModal(reportData, reportId, reportType);
                        showSuccess(`Successfully loaded ${reportType} report #${reportId}.`);
                        
                    } catch (err) {
                        console.error('Error:', err);
                        showError(`An error occurred while retrieving the ${reportType} report #${reportId}.`);
                    } finally {
                        hideLoading();
                    }
                });
            });
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
        content += `<h3>Patient Information</h3>`;
        
        if (reportData.patient_name) {
            content += `<p><strong>Name:</strong> ${reportData.patient_name}</p>`;
        }
        if (reportData.patient_id) {
            content += `<p><strong>CNP:</strong> ${reportData.patient_id}</p>`;
        }
        if (reportData.patient_code) {
            content += `<p><strong>Patient Code:</strong> ${reportData.patient_code}</p>`;
        }
        if (reportData.age) {
            content += `<p><strong>Age:</strong> ${reportData.age}</p>`;
        }
        if (reportData.gender) {
            content += `<p><strong>Gender:</strong> ${reportData.gender}</p>`;
        }
        if (reportData.sample_datetime) {
            content += `<p><strong>Sample Date/Time:</strong> ${reportData.sample_datetime}</p>`;
        }
        if (reportData.examination) {
            content += `<p><strong>Examination:</strong> ${reportData.examination}</p>`;
        }
        
        content += `</div>`;
        
        // Report results
        if (reportData.reports && reportData.reports.length > 0) {
            content += `<div class="report-section">`;
            content += `<h3>Results</h3>`;
            
            reportData.reports.forEach((report, index) => {
                content += `<p><strong>Investigation ${index + 1}:</strong> ${report.investigation || 'N/A'}</p>`;
                content += `<pre style="white-space: pre-wrap; background: var(--muted-background-color); padding: 0.75rem; border-radius: var(--border-radius);">${report.result || 'No result data'}</pre>`;
            });
            
            content += `</div>`;
        } else if (reportData.result) {
            content += `<div class="report-section">`;
            content += `<h3>Result</h3>`;
            content += `<pre style="white-space: pre-wrap; background: var(--muted-background-color); padding: 0.75rem; border-radius: var(--border-radius);">${reportData.result}</pre>`;
            content += `</div>`;
        }
        
        // Examiner information
        if (reportData.examiner) {
            content += `<div class="report-section">`;
            content += `<h3>Examiner</h3>`;
            content += `<p>${reportData.examiner}</p>`;
            content += `</div>`;
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
