# HippoBridge

HippoBridge is a medical data integration system that provides a modern web interface and FHIR-compatible API for accessing patient information from the Hipocrate medical system. It bridges the gap between legacy medical systems and modern healthcare data standards, enabling interoperability through standardized FHIR resources while providing both programmatic and user-friendly access to medical data.

## Features

- **Web Interface**: User-friendly web application for searching and viewing patient medical data
- **FHIR API**: Standards-compliant FHIR (Fast Healthcare Interoperability Resources) API for programmatic access
- **Patient Search**: Search patients by CNP (Personal Numerical Code), patient code, or name
- **Medical Data Access**: Retrieve patient information, medical analyses, diagnostic reports, and epicrisis
- **CNP Validation**: Built-in Romanian CNP validation with detailed information extraction
- **Authentication**: Secure authentication with the Hipocrate system
- **CLI Client**: Command-line interface for automated access to medical data

## Prerequisites

- Python 3.7+
- Access to Hipocrate medical system at `192.168.3.230`
- Hipocrate system credentials

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd hippobridge
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Environment Variables
Set the following environment variables:
- `HYP_USER`: Hipocrate system username
- `HYP_PASS`: Hipocrate system password

### Configuration Files
The application uses configuration files for server and service settings:
- `hipp.cfg`: Main configuration file with default settings
- `local.cfg`: Local overrides (optional, not tracked in version control)

Configuration file format:
```ini
[server]
port = 44660
host = 0.0.0.0

[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

## Usage

### Running the Server

Start the HippoBridge server:
```bash
python hipp.py
```

The server will start on `http://localhost:44660`

### Web Interface

Access the web interface at `http://localhost:44660` to:
- Search for patients using CNP, patient code, or name
- View patient information and medical analyses
- Access diagnostic reports and epicrisis

### API Endpoints

The FHIR-compatible API provides the following endpoints:

- `GET /fhir/Patient?q={search_term}` - Search for patients
- `GET /fhir/Patient/{id}` - Get patient information
- `GET /fhir/Observation?patient={patient_id}` - Get patient analyses
- `GET /fhir/DiagnosticReport?identifier={report_id}` - Get diagnostic report
- `GET /fhir/Encounter?identifier={encounter_id}` - Get encounter/checkout information
- `GET /fhir/ValueSet/cnp?id={cnp}` - Validate CNP
- `POST /fhir/login` - Authenticate with Hipocrate system

### Command-Line Client

Use the CLI client for programmatic access:
```bash
python client.py --username USER --password PASS --search "patient_name"
```

Available options:
- `--search` - Search for patients
- `--patient` - Retrieve patient information
- `--analyses` - Retrieve patient analyses
- `--report` - Retrieve diagnostic report
- `--checkout` - Retrieve checkout information
- `--cnp` - Validate CNP

## Development

### Project Structure

- `hipp.py` - Main server application with FHIR API endpoints
- `client.py` - Command-line client for accessing the API
- `static/` - Web interface files (HTML, CSS, JavaScript)
- `requirements.txt` - Python dependencies

### API Documentation

Access the OpenAPI specification at `http://localhost:44660/fhir/spec` when the server is running.

## License

This project is licensed for internal hospital use only.

## Acknowledgments

- Built using the FHIR standard for healthcare interoperability
- Uses aiohttp for asynchronous HTTP handling
- Uses BeautifulSoup for HTML parsing
