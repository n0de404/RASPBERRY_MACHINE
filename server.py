# server.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

APP = FastAPI(title="Machine Dashboard Server")

ACTIVE_TTL_SECONDS = 30  # client considered offline after 30s no heartbeat/event


@dataclass
class MachineSession:
    client_id: str
    machine_code: str
    machine_name: str
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    operator_id: Optional[str] = None
    pack_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None
    last_event: str = ""
    last_seen_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reject_breakdown"] = d["reject_breakdown"] or {}
        return d


SESSIONS: Dict[str, MachineSession] = {}  # key = machine_code
WS_CLIENTS: List[WebSocket] = []


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prune_dead_sessions():
    cutoff = utc_now() - timedelta(seconds=ACTIVE_TTL_SECONDS)
    dead = []
    for k, s in SESSIONS.items():
        try:
            t = datetime.fromisoformat(s.last_seen_utc)
        except Exception:
            t = utc_now()
        if t < cutoff:
            dead.append(k)
    for k in dead:
        del SESSIONS[k]


async def broadcast_state():
    prune_dead_sessions()
    payload = {
        "type": "STATE",
        "active_ttl_seconds": ACTIVE_TTL_SECONDS,
        "sessions": [s.to_dict() for s in SESSIONS.values()],
        "server_time_utc": utc_now().isoformat(),
    }
    living = []
    for ws in WS_CLIENTS:
        try:
            await ws.send_json(payload)
            living.append(ws)
        except Exception:
            pass
    WS_CLIENTS[:] = living


DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Machine Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 16px; }
    .top { display:flex; gap: 16px; align-items:center; margin-bottom: 12px; }
    .pill { padding: 6px 10px; border-radius: 999px; background: #eee; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 14px; }
    th { background: #f6f6f6; text-align: left; }
    .muted { color: #666; }
    .small { font-size: 12px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  </style>
</head>
<body>
  <div class="top">
    <h2 style="margin:0;">Machine Dashboard</h2>
    <div class="pill" id="conn">Connecting...</div>
    <div class="pill muted small" id="time"></div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Machine</th>
        <th>Job</th>
        <th>Operator</th>
        <th>Pack</th>
        <th>Butal</th>
        <th>Reject</th>
        <th>Reject Breakdown</th>
        <th>Last Event</th>
        <th>Last Seen (UTC)</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>

<script>
  const conn = document.getElementById("conn");
  const rows = document.getElementById("rows");
  const timeEl = document.getElementById("time");

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }

  function render(state){
    timeEl.textContent = "Server UTC: " + state.server_time_utc;
    rows.innerHTML = "";
    const sessions = state.sessions || [];
    sessions.sort((a,b)=> (a.machine_name||"").localeCompare(b.machine_name||""));

    for(const s of sessions){
      const r = document.createElement("tr");
      const rb = s.reject_breakdown || {};
      const rbText = Object.keys(rb).length
        ? Object.entries(rb).map(([k,v])=> `${k}:${v}`).join(", ")
        : "";
      r.innerHTML = `
        <td><div><b>${esc(s.machine_name)}</b></div><div class="muted small mono">${esc(s.machine_code)}</div></td>
        <td><div>${esc(s.job_name||"")}</div><div class="muted small mono">${esc(s.job_code||"")}</div></td>
        <td class="mono">${esc(s.operator_id||"")}</td>
        <td>${esc(s.pack_total)}</td>
        <td>${esc(s.butal_total)}</td>
        <td>${esc(s.reject_total)}</td>
        <td class="small">${esc(rbText)}</td>
        <td class="small">${esc(s.last_event||"")}</td>
        <td class="small mono">${esc(s.last_seen_utc||"")}</td>
      `;
      rows.appendChild(r);
    }
  }

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProto}://${location.host}/ws`);

  ws.onopen = () => { conn.textContent = "Connected"; conn.style.background = "#d6f5d6"; };
  ws.onclose = () => { conn.textContent = "Disconnected"; conn.style.background = "#ffd6d6"; };
  ws.onerror = () => { conn.textContent = "Error"; conn.style.background = "#ffd6d6"; };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if(msg.type === "STATE") render(msg);
  };
</script>
</body>
</html>
"""


@APP.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


@APP.get("/favicon.ico")
def favicon():
    # Return empty 204 so browser favicon requests don't pollute logs.
    return Response(status_code=204)


@APP.post("/api/event")
async def api_event(req: Request):
    """
    Expected JSON:
    {
      "client_id": "PI-01",
      "machine_code": "M00001",
      "machine_name": "Machine 01",
      "job_code": "101245",
      "job_name": "J024-0305",
      "operator_id": "1000001",
      "event": { ... },   # e.g. {"type":"PACK","qty":6}
      "last_event": "PACK +6"
    }
    """
    data = await req.json()

    machine_code = str(data.get("machine_code", "")).strip()
    if not machine_code:
        return JSONResponse({"ok": False, "error": "machine_code required"}, status_code=400)

    sess = SESSIONS.get(machine_code)
    if sess is None:
        sess = MachineSession(
            client_id=str(data.get("client_id", "UNKNOWN")),
            machine_code=machine_code,
            machine_name=str(data.get("machine_name", machine_code)),
            reject_breakdown={},
        )
        SESSIONS[machine_code] = sess

    # update common fields
    sess.client_id = str(data.get("client_id", sess.client_id))
    sess.machine_name = str(data.get("machine_name", sess.machine_name))
    sess.job_code = data.get("job_code", sess.job_code)
    sess.job_name = data.get("job_name", sess.job_name)
    sess.operator_id = data.get("operator_id", sess.operator_id)
    sess.last_seen_utc = utc_now().isoformat()
    sess.last_event = str(data.get("last_event", sess.last_event))

    # apply event counters if provided
    ev = data.get("event") or {}
    ev_type = str(ev.get("type", "")).upper()
    if ev_type == "PACK":
        sess.pack_total += int(ev.get("qty", 0) or 0)
    elif ev_type == "BUTAL":
        sess.butal_total += int(ev.get("qty", 0) or 0)
    elif ev_type == "REJECT":
        sess.reject_total += int(ev.get("qty", 1) or 1)
        reason = str(ev.get("reason", "")).strip()
        if reason:
            sess.reject_breakdown[reason] = sess.reject_breakdown.get(reason, 0) + int(ev.get("qty", 1) or 1)

    await broadcast_state()
    return {"ok": True}


@APP.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    WS_CLIENTS.append(ws)
    await broadcast_state()
    try:
        while True:
            # keep alive; client doesn't need to send anything
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in WS_CLIENTS:
            WS_CLIENTS.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:APP", host="0.0.0.0", port=8000, reload=False)
