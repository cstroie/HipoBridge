from fastapi import FastAPI
import uvicorn
import httpx
import asyncio
from typing import Dict, Any

app = FastAPI()

# Configuration
SERVICE_URL = "http://your-closed-source-service-url"  # Replace with actual service URL
PORT = 44660

# Create async HTTP client
client = httpx.AsyncClient()

@app.get("/")
async def root():
    return {"message": "Web API Interface to Closed Source Service"}

@app.get("/api/service")
async def call_service() -> Dict[str, Any]:
    try:
        response = await client.get(SERVICE_URL)
        return {
            "status": "success",
            "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/api/service")
async def post_to_service(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = await client.post(SERVICE_URL, json=data)
        return {
            "status": "success",
            "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
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
