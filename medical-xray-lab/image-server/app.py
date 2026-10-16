"""
Medical X-Ray Imaging Server & PACS Viewer GUI
Interfaces with the Modbus TCP / OpenPLC X-Ray Controller (`xray-modbus-controller`).
Serves ONLY X-ray images sourced from:
  - https://huggingface.co/datasets/HumynLabs/medical-imaging
  - https://huggingface.co/datasets/robailleo/medical-imaging-combined
"""

import datetime
import os
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, send_from_directory
from fetch_xrays import IMAGES_DIR, ingest_datasets

app = Flask(__name__)

# Optional defensive hardening toggle: when REQUIRE_PLC_TOKEN=true, PLC sync calls must provide X-PLC-Token
REQUIRE_PLC_TOKEN = os.environ.get("REQUIRE_PLC_TOKEN", "false").lower() == "true"
EXPECTED_PLC_TOKEN = os.environ.get("PLC_SHARED_TOKEN", "medlab-secure-plc-token-2026")

STUDIES = ingest_datasets()

PLC_STATE = {
    "controller_protocol": "Modbus TCP / OpenPLC (Port 5020)",
    "status_code": 1,
    "status_label": "READY",
    "kvp": 85,
    "mas": 12,
    "door_interlock_closed": True,
    "exposure_triggered": False,
    "selected_study_index": 0,
    "active_study_id": STUDIES[0]["study_id"] if STUDIES else "NONE",
    "last_sync_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "security_mode": "AUTHENTICATED (HARDENED)" if REQUIRE_PLC_TOKEN else "UNAUTHENTICATED (LAB DEFAULT)",
}

AUDIT_LOG = []


def record_audit(event_type: str, source_ip: str, detail: str) -> None:
    AUDIT_LOG.insert(
        0,
        {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "event": event_type,
            "source_ip": source_ip,
            "detail": detail,
        },
    )
    del AUDIT_LOG[40:]


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>MedPACS X-Ray Imaging Server & PLC Telemetry Console</title>
  <style>
    :root {
      --bg: #0b1120;
      --panel: #111827;
      --border: #1f2937;
      --accent: #38bdf8;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --warn: #f59e0b;
      --ok: #22c55e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      background: #0f172a;
      border-bottom: 1px solid var(--border);
    }
    header h1 {
      margin: 0;
      font-size: 1.25rem;
      color: var(--accent);
    }
    .badge {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      background: #1e293b;
      border: 1px solid #334155;
    }
    .container {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 20px;
      padding: 20px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .card h2 {
      margin-top: 0;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--accent);
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }
    .kv-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      font-size: 0.88rem;
      border-bottom: 1px dashed #1e293b;
    }
    .grid-studies {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
    }
    .study-card {
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      transition: border-color 0.2s;
    }
    .study-card.active {
      border: 2px solid var(--accent);
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.25);
    }
    .study-card img {
      width: 100%;
      height: 220px;
      object-fit: cover;
      background: #000;
      display: block;
    }
    .study-body {
      padding: 12px;
      font-size: 0.84rem;
    }
    .study-id {
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 4px;
    }
    .dataset-tag {
      display: inline-block;
      font-size: 0.72rem;
      padding: 2px 6px;
      border-radius: 4px;
      background: #1e293b;
      color: #93c5fd;
      margin-bottom: 6px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    th, td {
      text-align: left;
      padding: 8px;
      border-bottom: 1px solid var(--border);
    }
    th { color: var(--muted); }
    a { color: var(--accent); text-decoration: none; }
  </style>
  <script>
    async function refreshState() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('plc-status').textContent = data.plc.status_label;
        document.getElementById('plc-kvp').textContent = data.plc.kvp + ' kVp';
        document.getElementById('plc-mas').textContent = data.plc.mas + ' mAs';
        document.getElementById('plc-interlock').textContent = data.plc.door_interlock_closed ? 'CLOSED (SAFE)' : 'OPEN (FAULT)';
        document.getElementById('plc-active').textContent = data.plc.active_study_id + ' (Idx ' + data.plc.selected_study_index + ')';
        document.getElementById('plc-sync').textContent = data.plc.last_sync_utc;
        document.querySelectorAll('.study-card').forEach((el, idx) => {
          if (idx === data.plc.selected_study_index) {
            el.classList.add('active');
          } else {
            el.classList.remove('active');
          }
        });
      } catch (e) {}
    }
    setInterval(refreshState, 2000);
  </script>
</head>
<body>
  <header>
    <div>
      <h1>MedPACS X-Ray Archive & Modbus/OpenPLC Device Telemetry</h1>
      <div style="font-size: 0.8rem; color: var(--muted);">
        Modality Filter Enforced: <strong>DX / X-Ray Only</strong> |
        Sources:
        <a href="https://huggingface.co/datasets/HumynLabs/medical-imaging" target="_blank">HumynLabs/medical-imaging</a> &amp;
        <a href="https://huggingface.co/datasets/robailleo/medical-imaging-combined" target="_blank">robailleo/medical-imaging-combined</a>
      </div>
    </div>
    <span class="badge">{{ plc.security_mode }}</span>
  </header>

  <div class="container">
    <div>
      <div class="card">
        <h2>Modbus / OpenPLC Controller State</h2>
        <div class="kv-row"><span>Protocol</span><strong>{{ plc.controller_protocol }}</strong></div>
        <div class="kv-row"><span>Generator State (HR 0)</span><strong id="plc-status">{{ plc.status_label }}</strong></div>
        <div class="kv-row"><span>Tube Voltage (HR 1)</span><strong id="plc-kvp">{{ plc.kvp }} kVp</strong></div>
        <div class="kv-row"><span>Tube Current (HR 2)</span><strong id="plc-mas">{{ plc.mas }} mAs</strong></div>
        <div class="kv-row"><span>Selected Study (HR 3)</span><strong id="plc-active">{{ plc.active_study_id }} (Idx {{ plc.selected_study_index }})</strong></div>
        <div class="kv-row"><span>Door Interlock (Coil 0)</span><strong id="plc-interlock">{{ 'CLOSED (SAFE)' if plc.door_interlock_closed else 'OPEN (FAULT)' }}</strong></div>
        <div class="kv-row"><span>Last PLC Heartbeat</span><strong id="plc-sync" style="font-size:0.75rem">{{ plc.last_sync_utc }}</strong></div>
      </div>

      <div class="card">
        <h2>Controller API Endpoints</h2>
        <div class="kv-row"><span>GET /api/studies</span><span>List X-ray catalog</span></div>
        <div class="kv-row"><span>GET /api/active-study</span><span>Current PLC-staged X-ray</span></div>
        <div class="kv-row"><span>POST /api/plc-sync</span><span>Modbus PLC state push</span></div>
        <div class="kv-row"><span>GET /images/&lt;file&gt;</span><span>X-ray PNG file</span></div>
      </div>
    </div>

    <div>
      <div class="card">
        <h2>Curated X-Ray Studies ({{ studies|length }} Verified X-Ray Radiographs)</h2>
        <div class="grid-studies">
          {% for s in studies %}
          <div class="study-card {% if s.index == plc.selected_study_index %}active{% endif %}">
            <a href="/images/{{ s.filename }}" target="_blank">
              <img src="/images/{{ s.filename }}" alt="{{ s.study_id }}" />
            </a>
            <div class="study-body">
              <div class="study-id">[HR3={{ s.index }}] {{ s.study_id }}</div>
              <span class="dataset-tag">{{ s.dataset_source }}</span>
              <span class="dataset-tag">Modality: {{ s.modality }}</span>
              <p style="margin: 6px 0 0; color: var(--muted); line-height: 1.35;">{{ s.findings }}</p>
            </div>
          </div>
          {% endfor %}
        </div>
      </div>

      <div class="card">
        <h2>Controller &amp; Access Audit Log</h2>
        <table>
          <thead>
            <tr><th>Timestamp</th><th>Event</th><th>Source IP</th><th>Details</th></tr>
          </thead>
          <tbody>
            {% for log in audit_log[:12] %}
            <tr>
              <td>{{ log.timestamp }}</td>
              <td>{{ log.event }}</td>
              <td>{{ log.source_ip }}</td>
              <td>{{ log.detail }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    record_audit("GUI_VIEW", request.remote_addr or "unknown", "Operator viewed MedPACS X-Ray GUI")
    return render_template_string(HTML_TEMPLATE, studies=STUDIES, plc=PLC_STATE, audit_log=AUDIT_LOG)


@app.route("/images/<path:filename>")
def serve_image(filename: str):
    record_audit("IMAGE_FETCH", request.remote_addr or "unknown", f"Requested X-ray image file: {filename}")
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/api/status")
def api_status():
    return jsonify({"plc": PLC_STATE, "total_xrays": len(STUDIES), "audit_log": AUDIT_LOG[:10]})


@app.route("/api/studies")
def api_studies():
    record_audit("API_STUDIES_LIST", request.remote_addr or "unknown", "Queried X-ray study catalog")
    return jsonify({"modality_filter": "X-ray only", "count": len(STUDIES), "studies": STUDIES})


@app.route("/api/active-study")
def api_active_study():
    idx = PLC_STATE["selected_study_index"] % max(len(STUDIES), 1)
    study = STUDIES[idx] if STUDIES else {}
    record_audit(
        "API_ACTIVE_STUDY",
        request.remote_addr or "unknown",
        f"Retrieved PLC-staged study index={idx} ({study.get('study_id', 'N/A')})",
    )
    return jsonify({
        "plc_state": PLC_STATE,
        "active_study": study,
        "image_download_path": f"/images/{study.get('filename', '')}",
    })


@app.route("/api/plc-sync", methods=["POST"])
def api_plc_sync():
    if REQUIRE_PLC_TOKEN:
        token = request.headers.get("X-PLC-Token", "")
        if token != EXPECTED_PLC_TOKEN:
            record_audit("PLC_AUTH_REJECTED", request.remote_addr or "unknown", "Missing or invalid X-PLC-Token")
            return jsonify({"error": "Unauthorized PLC request"}), 401

    payload = request.get_json(silent=True) or {}
    idx = int(payload.get("selected_study_index", 0))
    if STUDIES:
        idx = max(0, min(idx, len(STUDIES) - 1))
        active_study = STUDIES[idx]
        active_id = active_study["study_id"]
        image_path = f"/images/{active_study['filename']}"
    else:
        active_id = "NONE"
        image_path = ""

    PLC_STATE.update({
        "status_code": int(payload.get("status_code", 1)),
        "status_label": str(payload.get("status_label", "READY")),
        "kvp": int(payload.get("kvp", 85)),
        "mas": int(payload.get("mas", 12)),
        "door_interlock_closed": bool(payload.get("door_interlock_closed", True)),
        "exposure_triggered": bool(payload.get("exposure_triggered", False)),
        "selected_study_index": idx,
        "active_study_id": active_id,
        "last_sync_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    if payload.get("exposure_triggered"):
        record_audit(
            "PLC_EXPOSURE_TRIGGER",
            request.remote_addr or "unknown",
            f"Modbus Coil 1 triggered staging of Study[{idx}]={active_id} at {PLC_STATE['kvp']} kVp / {PLC_STATE['mas']} mAs",
        )

    return jsonify({
        "synced": True,
        "active_study_id": active_id,
        "selected_study_index": idx,
        "image_path": image_path,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
