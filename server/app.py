"""
Web server for the AI coding agent.

Routes:
  POST /api/sessions                      -> start a new agent run, returns {session_id}
  GET  /api/sessions/{id}                  -> current status + full event history so far
  GET  /api/sessions/{id}/verification       -> structured, machine-readable verification result
  WS   /api/sessions/{id}/stream            -> live event stream for the frontend to render
  GET  /api/sessions/{id}/report             -> verification report content, once generated
  GET  /api/sessions/{id}/evidence/{path}     -> serves a screenshot/video evidence file

  Mode 1 (Agent Interface) -> see server/agent_interface.py for the full route list
  Mode 2 (IDE Mode)         -> see server/ide_mode.py for the full route list

Serves the static frontend (server/static/index.html) at '/'.

This is intentionally a thin layer: all real logic lives in the
existing agent/ package, which is otherwise completely unchanged — only
AgentController gained an optional on_event parameter, and main.py's
CLI behavior is untouched since it never passes one.

IMPORTANT: importing this module constructs the configured provider
(via server/dependencies.py), which requires a valid API key for
whichever provider DEFAULT_MODEL selects. If that key is missing, this
module — and therefore the whole server — will fail to import with a
clear RuntimeError, on purpose (fail fast at startup, not on the first
real request). Constructing a provider object never itself makes an API
call; only handling an actual request does.

Run with:
    uvicorn server.app:app --reload
"""

import asyncio
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.session_manager import SessionManager
from server import agent_interface, ide_mode

app = FastAPI(title="AI Coding Agent Console")
manager = SessionManager()
app.include_router(agent_interface.router)
app.include_router(ide_mode.router)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class NewSessionRequest(BaseModel):
    request: str


@app.post("/api/sessions")
def create_session(payload: NewSessionRequest):
    if not payload.request or not payload.request.strip():
        return JSONResponse({"error": "request text is required"}, status_code=400)
    session_id = manager.create_session(payload.request.strip())
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = manager.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return {
        "id": session.id,
        "request": session.request,
        "status": session.status,
        "events": session.events,
        "result": session.result,
        "verification_result": session.verification_result,
    }


@app.get("/api/sessions/{session_id}/verification")
def get_verification_result(session_id: str):
    """
    The clean, agent-facing pull for a structured verdict: an external
    coding agent (Claude Code, Codex, a Cursor agent, etc.) can poll this
    one URL for exactly the machine_readable object generate_report()
    produces — schema_version, status, tests, errors, evidence, and
    suggested_next_action — without needing to parse the full session
    object or search its event log.
    """
    session = manager.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)
    if session.verification_result is None:
        return JSONResponse({"error": "verification result not yet available"}, status_code=404)
    return session.verification_result


@app.websocket("/api/sessions/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str):
    await websocket.accept()

    q = manager.subscribe(session_id)
    if q is None:
        await websocket.send_json({"type": "error", "message": "session not found"})
        await websocket.close()
        return

    loop = asyncio.get_event_loop()
    try:
        while True:
            # q.get() is a blocking call from a plain queue.Queue (session
            # events come from a background thread, not asyncio) — running
            # it in an executor keeps the event loop free for other
            # connections while this one waits.
            event = await loop.run_in_executor(None, q.get)
            await websocket.send_json(event)
            if event.get("type") in ("session_done", "session_error"):
                break
    except WebSocketDisconnect:
        pass


@app.get("/api/sessions/{session_id}/report")
def get_report(session_id: str):
    session = manager.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)

    report_path = os.path.join(session.workspace_root, ".sandbox", "verification_report.md")
    if not os.path.isfile(report_path):
        return JSONResponse({"error": "report not generated yet"}, status_code=404)

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}


@app.get("/api/sessions/{session_id}/evidence/{filename:path}")
def get_evidence(session_id: str, filename: str):
    session = manager.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)

    evidence_root = os.path.abspath(os.path.join(session.workspace_root, ".sandbox", "evidence"))

    # Screenshot/video paths are stored (and returned in verification
    # results) as paths relative to the workspace root, e.g.
    # ".sandbox/evidence/01-homepage.png" — but this endpoint's own URL
    # already scopes it to the evidence directory, so strip that prefix
    # if it's present rather than joining it on top of evidence_root
    # (which was doubling the path and causing every lookup to 404).
    normalized = filename
    for prefix in (".sandbox/evidence/", ".sandbox\\evidence\\"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    full_path = os.path.abspath(os.path.join(evidence_root, normalized))

    # Same path-escape protection pattern used throughout the rest of
    # this project (see Workspace.resolve) — never serve a file outside
    # this session's own evidence directory.
    if not (full_path == evidence_root or full_path.startswith(evidence_root + os.sep)):
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if not os.path.isfile(full_path):
        return JSONResponse({"error": "not found"}, status_code=404)

    return FileResponse(full_path)

# Registered last so it acts as a fallback for '/' and any other static
# asset, without shadowing the API routes declared above.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")