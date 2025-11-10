// CNP validation function (moved from server-side)
function validateCNP(cnp) {
    // Check if CNP is exactly 13 digits
    if (!cnp || cnp.length !== 13 || !/^\d+$/.test(cnp)) {
        return false;
    }
    
    // Extract components
    const genderDigit = parseInt(cnp[0]);
    const year = parseInt(cnp.substring(1, 3));
    const month = parseInt(cnp.substring(3, 5));
    const day = parseInt(cnp.substring(5, 7));
    const countyCode = parseInt(cnp.substring(7, 9));
    
    // Validate gender digit (1-8 are valid)
    if (genderDigit < 1 || genderDigit > 8) {
        return false;
    }
    
    // Validate month (1-12)
    if (month < 1 || month > 12) {
        return false;
    }
    
    // Validate day (1-31)
    if (day < 1 || day > 31) {
        return false;
    }
    
    // Validate county code (1-52, excluding 47-50, plus 70-79 for diaspora, 90-99 for special cases)
    if (!((countyCode >= 1 && countyCode <= 52 && !(countyCode >= 47 && countyCode <= 50)) || 
          (countyCode >= 70 && countyCode <= 79) || 
          (countyCode >= 90 && countyCode <= 99))) {
        return false;
    }
    
    // Validate date by trying to create a date object
    try {
        // Determine century based on gender digit
        let fullYear;
        if (genderDigit === 1 || genderDigit === 2) {
            fullYear = 1900 + year;
        } else if (genderDigit === 3 || genderDigit === 4) {
            fullYear = 1800 + year;
        } else if (genderDigit === 5 || genderDigit === 6) {
            fullYear = 2000 + year;
        } else { // 7, 8
            fullYear = 2000 + year; // For people born after 2000
        }
        
        // Check if date is valid
        const date = new Date(fullYear, month - 1, day);
        if (date.getFullYear() !== fullYear || 
            date.getMonth() !== month - 1 || 
            date.getDate() !== day) {
            return false;
        }
    } catch (e) {
        return false;
    }
    
    // Validate control digit using checksum
    const weights = [2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9];
    let checksum = 0;
    for (let i = 0; i < 12; i++) {
        checksum += parseInt(cnp[i]) * weights[i];
    }
    checksum %= 11;
    const controlDigit = checksum === 10 ? 1 : checksum;
    
    return controlDigit === parseInt(cnp[12]);
}

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
        
        // Validate CNP format - either 13-digit CNP or partial CNP ending with *
        if (!cnp || (!/^\d{13}$/.test(cnp) && !/^\d+\*$/.test(cnp))) {
            showError('Please enter a valid 13-digit CNP or partial CNP (digits followed by *)');
            return;
        }
        
        // Show loading state
        showLoading();
        hideError();
        hideSuccess();
        results.style.display = 'none';
        
        try {
            // For partial CNP searches (ending with *), skip CNP validation
            if (!cnp.endsWith('*')) {
                // Validate CNP using client-side function
                if (!validateCNP(cnp)) {
                    showError('Invalid CNP. Please check the number and try again.');
                    return;
                }
                
                showSuccess('Valid CNP detected. Retrieving patient information...');
            } else {
                showSuccess('Searching for patient with partial CNP...');
            }
            
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
                showError('No patient found with this search term.');
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
            await displayPatientData(patientData, analysesData);
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
    
    async function displayPatientData(patientData, analysesData) {
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
                        // Fetch report data
                        const reportResponse = await fetch(`/api/reports?id=${analysis.report_id}`);
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
                            reportData.reports.forEach((report, index) => {
                                cardContent += `<p><strong>${report.investigation || 'Investigation'}:</strong></p>`;
                                if (report.result) {
                                    cardContent += `<p>${report.result}</p>`;
                                }
                            });
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
