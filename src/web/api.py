"""FastAPI backend for CAPL Pipeline V2.2.

Provides REST and WebSocket endpoints for the web UI.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="CAPL Pipeline V2.2",
    description="CAPL test case generation pipeline for CANoe projects",
    version="2.2.0"
)

# Global state (would be managed by dependency injection in production)
_state: Dict[str, Any] = {
    "registry": None,
    "llm_router": None,
    "config_builder": None,
}


# Pydantic models for API
class SignalRequest(BaseModel):
    name: str
    bus_type: Optional[str] = None
    ecu_node: Optional[str] = None
    env_var_name: Optional[str] = None
    sys_var_path: Optional[str] = None


class GapQuestionRequest(BaseModel):
    gap_id: str
    gap_type: str
    context: Dict[str, Any]


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


# REST Endpoints
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.2.0"}


@app.get("/api/signals")
async def list_signals(
    bus_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """List all signals in registry."""
    registry = _state.get("registry")
    if not registry:
        return {"signals": [], "total": 0}

    signals = registry.get_all_signals()

    # Filter
    if bus_type:
        signals = [s for s in signals if s.bus_type == bus_type]
    if status:
        signals = [s for s in signals if s.status == status]

    # Limit
    signals = signals[:limit]

    return {
        "signals": [s.model_dump() for s in signals],
        "total": len(signals)
    }


@app.post("/api/signals")
async def register_signal(request: SignalRequest):
    """Register a new signal."""
    registry = _state.get("registry")
    if not registry:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    signal = registry.register(
        name=request.name,
        bus_type=request.bus_type,
        ecu_node=request.ecu_node,
        env_var_name=request.env_var_name,
        sys_var_path=request.sys_var_path
    )

    return {"signal": signal.model_dump(), "created": True}


@app.get("/api/signals/{signal_name}")
async def get_signal(signal_name: str):
    """Get signal details."""
    registry = _state.get("registry")
    if not registry:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    signal = registry.lookup(signal_name)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_name}' not found")

    return {"signal": signal.model_dump()}


@app.get("/api/config/gaps")
async def get_gaps():
    """Get current configuration gaps."""
    registry = _state.get("registry")
    if not registry:
        return {"gaps": [], "total": 0}

    report = registry.export_report()
    return {
        "gaps": report.get("gap_signals", []),
        "total": len(report.get("gap_signals", [])),
        "by_status": report.get("by_status", {})
    }


@app.post("/api/config/gaps/{gap_id}/resolve")
async def resolve_gap(gap_id: str, resolution: Dict[str, Any]):
    """Resolve a configuration gap."""
    # This would be implemented with the config builder
    return {
        "gap_id": gap_id,
        "status": "resolved",
        "resolution": resolution
    }


@app.get("/api/config/status")
async def get_config_status():
    """Get configuration status."""
    registry = _state.get("registry")
    if not registry:
        return {"status": "not_initialized"}

    report = registry.export_report()
    return {
        "status": "active",
        "signal_count": report.get("total_signals", 0),
        "by_status": report.get("by_status", {}),
        "by_source": report.get("by_source", {})
    }


@app.get("/api/templates")
async def list_templates():
    """List available CAPL templates."""
    from ..capl.template_engine import TemplateEngine

    engine = TemplateEngine()
    templates = engine.get_available_templates()

    return {"templates": templates}


# WebSocket for chat
class ConnectionManager:
    """Manage WebSocket connections for chat."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store a WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific connection."""
        await websocket.send_json(message)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connections."""
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for chat-based gap resolution."""
    await manager.connect(websocket)

    try:
        # Send welcome message
        await manager.send_message(websocket, {
            "type": "system",
            "content": "Connected to CAPL Pipeline chat. How can I help you?"
        })

        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("content", "")
            gap_id = data.get("gap_id")

            # Process message (simplified - actual implementation would use ChatResolver)
            await manager.send_message(websocket, {
                "type": "assistant",
                "content": f"Processing: {message}",
                "gap_id": gap_id
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected: {session_id}")


@app.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for job progress updates."""
    await manager.connect(websocket)

    try:
        # Send initial progress
        await manager.send_message(websocket, {
            "type": "progress",
            "job_id": job_id,
            "progress": 0,
            "status": "started"
        })

        # In production, this would track actual job progress
        for i in range(1, 11):
            await asyncio.sleep(0.5)
            await manager.send_message(websocket, {
                "type": "progress",
                "job_id": job_id,
                "progress": i * 10,
                "status": "running"
            })

        await manager.send_message(websocket, {
            "type": "progress",
            "job_id": job_id,
            "progress": 100,
            "status": "completed"
        })

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Serve static files (Vue SPA)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="spa")


def init_app(registry=None, llm_router=None, config_builder=None):
    """Initialize app with dependencies."""
    _state["registry"] = registry
    _state["llm_router"] = llm_router
    _state["config_builder"] = config_builder
