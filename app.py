"""
FastAPI Backend for Nexus Banking Cockpit.
Directly interfaces with the single-page Nexus Cockpit UI.
Supports:
- POST /chat & POST /api/chat
- POST /reset & POST /api/reset
- GET /api/health
"""

import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from backend.core.ledger_db import db
from backend.agents.supervisor import supervisor_agent
from backend.models.llm_service import llm_service

app = FastAPI(
    title="Nexus Banking Cockpit API",
    description="Real-time multi-agent backend serving the Nexus Banking Cockpit.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatInput(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    approved: Optional[bool] = False


@app.middleware("http")
async def add_correlation_tracing(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", f"TX-{uuid.uuid4().hex[:4].upper()}")
    response: Response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response


@app.get("/api/health")
@app.get("/health")
def health_check():
    return {
        "status": "online",
        "has_api_key": llm_service.has_api_key(),
        "model": llm_service.model_name
    }


@app.post("/chat")
@app.post("/api/chat")
def handle_chat(req: ChatInput, request: Request):
    text = req.message or req.query
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    cid = request.headers.get("x-correlation-id", f"TX-{uuid.uuid4().hex[:4].upper()}")
    result = supervisor_agent.dispatch(message=text.strip(), correlation_id=cid, approved=bool(req.approved))
    return result


@app.post("/reset")
@app.post("/api/reset")
def handle_reset():
    db.reset_to_seed_data()
    acc = db.get_account("ACC-1001")
    card = list(db.cards.values())[0]
    return {
        "status": "ok",
        "balance": acc["balance"],
        "card_status": card["status"]
    }


@app.get("/api/state")
def get_state(customer_id: str = "CUST-001"):
    return db.get_full_state(customer_id)


# Mount static frontend
CURRENT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = CURRENT_DIR.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port)
