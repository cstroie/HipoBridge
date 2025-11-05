from fastapi import FastAPI
import uvicorn
import httpx
import asyncio
from typing import Dict, Any

app = FastAPI()

# Configuration
SERVICE_URL = "http://192.168.3.230/hipocrate"  # Updated to Hipocrate service URL
PORT = 44660

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

@app.get("/api/service")
async def call_service() -> Dict[str, Any]:
    try:
        response = await client.get(SERVICE_URL, headers=HEADERS)
        return {
            "status": "success",
            "data": response.text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/api/service")
async def post_to_service(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = await client.post(SERVICE_URL, json=data, headers=HEADERS)
        return {
            "status": "success",
            "data": response.text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
