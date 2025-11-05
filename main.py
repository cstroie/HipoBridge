import os
from urllib.parse import urljoin
from fastapi import FastAPI
import uvicorn
import httpx
import asyncio
from typing import Dict, Any

app = FastAPI()

# Configuration
SERVICE_URL = "http://192.168.3.230/hipocrate"  # Updated to Hipocrate service URL
PORT = 44660

# Get credentials from environment variables
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

# Headers for compatibility with Hipocrate service
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Create async HTTP client
client = httpx.AsyncClient()

@app.get("/")
async def root():
    return {"message": "Web API Interface to Hipocrate Service"}

def is_login_page(content: str) -> bool:
    """Detect if we're on the login page"""
    return "RECUPERARE PAROLA" in content and "Username" in content and "Password" in content

async def login_if_needed() -> bool:
    """Attempt to login if we're on the login page"""
    if not HYP_USER or not HYP_PASS:
        return False
    
    try:
        # Prepare login data
        login_data = {
            "username": HYP_USER,
            "password": HYP_PASS
        }
        
        # Submit login form
        login_response = await client.post(
            SERVICE_URL, 
            data=login_data, 
            headers=HEADERS
        )
        
        # Check if login was successful (not redirected back to login page)
        if not is_login_page(login_response.text):
            return True
        return False
    except Exception:
        return False

async def handle_service_request(method: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Handle service requests with automatic login"""
    try:
        # Make initial request
        if method == "GET":
            response = await client.get(SERVICE_URL, headers=HEADERS)
        else:  # POST
            response = await client.post(SERVICE_URL, json=data, headers=HEADERS)
        
        # Check if we got redirected to login page
        if is_login_page(response.text):
            # Try to login
            login_success = await login_if_needed()
            if login_success:
                # Retry the original request
                if method == "GET":
                    response = await client.get(SERVICE_URL, headers=HEADERS)
                else:  # POST
                    response = await client.post(SERVICE_URL, json=data, headers=HEADERS)
                
                # Check if login was successful after retry
                if is_login_page(response.text):
                    return {
                        "status": "error",
                        "message": "Login failed or session expired"
                    }
            else:
                return {
                    "status": "error",
                    "message": "Login required but failed"
                }
        
        return {
            "status": "success",
            "data": response.text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/service")
async def call_service() -> Dict[str, Any]:
    return await handle_service_request("GET")

@app.post("/api/service")
async def post_to_service(data: Dict[str, Any]) -> Dict[str, Any]:
    return await handle_service_request("POST", data)

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
