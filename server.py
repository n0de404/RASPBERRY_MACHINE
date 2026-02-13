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
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Machine Status & Analytics</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    html, body { height: 100%; margin: 0; }
    body { font-family: "Poppins", sans-serif; background: #f8f8f8; color: #333; display: flex; flex-direction: column; }
    .diagnostics { padding: 16px 20px; background: #e9ecef; border-bottom: 1px solid #d9d9d9; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .diag-item { background: #fff; border-radius: 10px; padding: 10px 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); font-size: 13px; }
    .diag-item .value { font-weight: 700; margin-top: 6px; }
    .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .connected { background: #4CAF50; }
    .disconnected { background: #f44336; }
    .main-tabs { display: flex; gap: 10px; padding: 14px 20px 10px; flex-wrap: wrap; }
    .main-tab-button { background: #e1e5ef; border: none; border-radius: 20px; padding: 8px 18px; font-weight: 600; cursor: pointer; }
    .main-tab-button.active { background: #1f8ef1; color: #fff; }
    .main-tab-content { display: none; padding: 0 20px 20px; }
    .main-tab-content.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 12px; }
    .card { background: #fff; border-radius: 12px; padding: 16px; border: 2px solid transparent; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .card.active { border-color: #4CAF50; }
    .card.stopped { border-color: #f44336; }
    .card.maintenance { border-color: #FF9800; }
    .card h3 { margin: 0 0 10px; font-size: 1.05rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }
    .card p { margin: 6px 0; font-size: 0.9rem; }
    .panel { margin-top: 14px; background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .panel h3 { margin: 0 0 6px; }
    .muted { color: #666; font-size: 0.9rem; }
    .placeholder { border: 1px dashed #d9d9d9; border-radius: 10px; padding: 14px; color: #777; background: #fafafa; margin-top: 12px; }
    @media (max-width: 1400px) { .grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    @media (max-width: 768px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .main-tab-content { padding: 0 12px 12px; } .main-tabs { padding: 12px; } .diagnostics { padding: 12px; } }
  </style>
</head>
<body>
  <div class="diagnostics">
    <div class="diag-item">Client Status<div class="value" id="client-status"><span class="status-dot disconnected"></span>Connecting...</div></div>
    <div class="diag-item">Server Time<div class="value" id="time">N/A</div></div>
    <div class="diag-item">Last Message<div class="value" id="last-message">N/A</div></div>
    <div class="diag-item">Machine Count<div class="value" id="machine-count">0</div></div>
  </div>

  <div class="main-tabs">
    <button class="main-tab-button active" data-target="machinesTab">Machines</button>
    <button class="main-tab-button" data-target="jobQueueTab">Job Queue</button>
    <button class="main-tab-button" data-target="finishedJobsTab">Finished Jobs</button>
    <button class="main-tab-button" data-target="archivedJobsTab">Archived Jobs</button>
    <button class="main-tab-button" data-target="pdrTab">PDR Reports</button>
  </div>

  <div id="machinesTab" class="main-tab-content active">
    <div class="grid" id="machineGrid"></div>
  </div>

  <div id="jobQueueTab" class="main-tab-content">
    <div class="panel">
      <h3>Job Queue Map</h3>
      <div class="muted">UI shell ready. Queue data wiring can be added next.</div>
      <div class="placeholder">Queue map placeholder</div>
    </div>
    <div class="panel">
      <h3>Auto-Assign Job</h3>
      <div class="placeholder">Form placeholder</div>
    </div>
  </div>

  <div id="finishedJobsTab" class="main-tab-content">
    <div class="panel">
      <h3>Finished Job Confirmation</h3>
      <div class="placeholder">Finished jobs list placeholder</div>
    </div>
  </div>

  <div id="archivedJobsTab" class="main-tab-content">
    <div class="panel">
      <h3>Archived Jobs</h3>
      <div class="placeholder">Archived jobs list placeholder</div>
    </div>
  </div>

  <div id="pdrTab" class="main-tab-content">
    <div class="panel">
      <h3>Production Daily Reports</h3>
      <div class="placeholder">PDR table and print-preview placeholder</div>
    </div>
  </div>

<script>
  const clientStatus = document.getElementById("client-status");
  const timeEl = document.getElementById("time");
  const lastMessageEl = document.getElementById("last-message");
  const machineCountEl = document.getElementById("machine-count");
  const machineGrid = document.getElementById("machineGrid");
  const MACHINE_CODES = Array.from({length: 23}, (_, i) => `M${String(i + 1).padStart(5, "0")}`);

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }

  function statusClass(lastSeenUtc){
    if(!lastSeenUtc) return "stopped";
    const seen = new Date(lastSeenUtc).getTime();
    if(Number.isNaN(seen)) return "stopped";
    const ageSec = (Date.now() - seen) / 1000;
    return ageSec <= 30 ? "active" : "stopped";
  }

  function render(state){
    timeEl.textContent = "Server UTC: " + state.server_time_utc;
    machineGrid.innerHTML = "";
    const sessions = state.sessions || [];
    const byCode = Object.fromEntries(sessions.map(s => [String(s.machine_code || "").trim(), s]));
    machineCountEl.textContent = String(MACHINE_CODES.length);

    for(const code of MACHINE_CODES){
      const s = byCode[code] || {
        machine_code: code,
        machine_name: `Machine ${parseInt(code.slice(1), 10) || code}`,
        job_name: "",
        operator_id: "",
        pack_total: 0,
        butal_total: 0,
        reject_total: 0,
        last_event: "No data yet",
        last_seen_utc: "",
      };
      const css = statusClass(s.last_seen_utc) || "stopped";
      const card = document.createElement("div");
      card.className = `card ${css}`;
      const total = Number(s.pack_total||0) + Number(s.butal_total||0) + Number(s.reject_total||0);
      card.innerHTML = `
        <h3>${esc(s.machine_name || s.machine_code)}</h3>
        <p>Machine: <strong>${esc(s.machine_code || code)}</strong></p>
        <p>Job: <strong>${esc(s.job_name || "No Job Set")}</strong></p>
        <p>Operator: <strong>${esc(s.operator_id || "-")}</strong></p>
        <p>Status: <strong>${css.toUpperCase()}</strong></p>
        <p>Pack: <strong>${esc(s.pack_total)}</strong></p>
        <p>Butal: <strong>${esc(s.butal_total)}</strong></p>
        <p>Reject: <strong>${esc(s.reject_total)}</strong></p>
        <p>Total: <strong>${esc(total)}</strong></p>
        <p class="muted">Last Event: ${esc(s.last_event || "-")}</p>
      `;
      machineGrid.appendChild(card);
    }
  }

  // tab handling
  document.querySelectorAll(".main-tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-target");
      document.querySelectorAll(".main-tab-button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".main-tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(target)?.classList.add("active");
    });
  });

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProto}://${location.host}/ws`);

  ws.onopen = () => { clientStatus.innerHTML = '<span class="status-dot connected"></span>Connected'; };
  ws.onclose = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Disconnected'; };
  ws.onerror = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Error'; };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    lastMessageEl.textContent = "STATE";
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
