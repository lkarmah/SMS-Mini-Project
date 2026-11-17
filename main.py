import os
import re
from datetime import datetime, timezone
from typing import List, Optional
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text, create_engine, desc
from sqlalchemy.orm import declarative_base, sessionmaker, Session

load_dotenv()

# ==========================================
# 1. Configuration
# ==========================================
SMS_API_KEY = os.getenv("SMS_API_KEY", "7tNubPy_3gjgTCbu-ehD6GzgsZNAcFasdkk_gKH6PbkcDzPc8-LDHYxxI3oFJqJg").strip()
SENDER_IDS = [s.strip() for s in os.getenv("SENDER_IDS", "Kelly").split(",") if s.strip()]
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "").rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/messages.db")
NALO_ENDPOINT = os.getenv(
    "NALO_ENDPOINT",
    os.getenv("NALO_API_URL", "https://sms.nalosolutions.com/smsbackend/clientapi/Resl_Nalo/send-message/")
).strip()
AUTO_RECONCILE = os.getenv("AUTO_RECONCILE", "true").lower() in ("true", "1", "yes")

# ==========================================
# 2. Database Models (SQLite / PostgreSQL)
# ==========================================
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), index=True, nullable=False)
    sender_id = Column(String(50), nullable=False)
    recipient = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="SUBMITTED", nullable=False)
    status_code = Column(String(50), nullable=True)
    sent_at = Column(String(100), nullable=False)
    delivered_at = Column(String(100), nullable=True)
    raw_response = Column(Text, nullable=True)
    raw_callback = Column(Text, nullable=True)

class DeliveryReport(Base):
    __tablename__ = "delivery_reports"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), index=True, nullable=False)
    recipient = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False)
    status_code = Column(String(50), nullable=True)
    received_at = Column(String(100), nullable=False)
    payload = Column(Text, nullable=True)

# Safe directory creation for SQLite
if DATABASE_URL.startswith("sqlite"):
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_file_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 3. FastAPI App & Pydantic Schemas
# ==========================================
app = FastAPI(
    title="Nalo SMS Gateway API",
    description="SMS platform for dispatching messages and handling delivery reports via Nalo Solutions.",
    version="1.1.0"
)
@app.get("/api/health")
def health():
    return{"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SendSmsRequest(BaseModel):
    numbers: str = Field(..., description="Comma-separated Ghanaian numbers (e.g. 0244123456 or 233XXXXXXXXX)")
    senderId: str = Field(..., description="Approved Sender ID")
    message: str = Field(..., min_length=1, max_length=1600)

def normalize_number(phone: str) -> Optional[str]:
    """
    Normalizes Ghanaian phone numbers into the 233XXXXXXXXX standard.
    Handles:
      - 024XXXXXXX (10 digits starting with 0) -> 23324XXXXXXX
      - 24XXXXXXX  (9 digits) -> 23324XXXXXXX
      - 233XXXXXXXXX (12 digits)
      - 00233XXXXXXXXX (14 digits) -> 233XXXXXXXXX
      - +233XXXXXXXXX -> 233XXXXXXXXX
    """
    clean = re.sub(r"\D", "", phone)
    if clean.startswith("00233") and len(clean) == 14:
        clean = clean[2:]
    elif clean.startswith("0") and len(clean) == 10:
        clean = "233" + clean[1:]
    elif len(clean) == 9 and not clean.startswith("0"):
        clean = "233" + clean
    if re.match(r"^233\d{9}$", clean):
        return clean
    return None

def parse_dlr_status(status_str: str) -> str:
    """Accurately maps DLR status tokens without false substring matches."""
    s = (status_str or "").upper().strip()
    if s in ("DELIVRD", "DELIVERED", "SUCCESS"):
        return "DELIVRD"
    if any(k in s for k in ("UNDELIV", "FAIL", "REJECT", "EXPIRED", "DELETED")):
        return "FAILED"
    if s.startswith("DELIV"):
        return "DELIVRD"
    if any(k in s for k in ("ACCEPT", "PEND", "SUBMIT")):
        return "SUBMITTED"
    return s[:50]

# ==========================================
# 4. Web UI Dashboard Endpoint
# ==========================================
@app.get("/", response_class=HTMLResponse)
def index_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Gateway Dashboard By Kelly</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text-main);
            padding: 30px 20px;
        }
        .container {
            max-width: 1100px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border);
        }
        .header h1 {
            font-size: 24px;
            font-weight: 700;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header-links a {
            color: var(--primary);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            margin-left: 15px;
            padding: 6px 12px;
            border-radius: 6px;
            background: #eff6ff;
        }
        .header-links a:hover {
            background: #dbeafe;
        }
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 18px 20px;
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .stat-card .label { font-size: 13px; font-weight: 500; color: var(--text-muted); }
        .stat-card .value { font-size: 26px; font-weight: 700; margin-top: 6px; }
        .stat-card.delivered .value { color: var(--success); }
        .stat-card.pending .value { color: var(--warning); }
        .stat-card.failed .value { color: var(--danger); }

        /* Main Content Layout */
        .layout {
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 25px;
        }
        @media (max-width: 900px) {
            .layout { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .card h2 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            color: #1e293b;
        }
        /* Form */
        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 6px;
            color: #334155;
        }
        .form-group {
            margin-bottom: 16px;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-family: inherit;
            font-size: 14px;
            color: #1e293b;
            background: #fff;
            transition: border-color 0.15s;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
        }
        .helper-text {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        .msg-meta {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 5px;
        }
        button.btn-primary {
            width: 100%;
            background: var(--primary);
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 12px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }
        button.btn-primary:hover { background: var(--primary-hover); }
        button.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

        /* Alert notifications */
        .alert {
            margin-top: 15px;
            padding: 12px 14px;
            border-radius: 8px;
            font-size: 13px;
            display: none;
        }
        .alert.success { background: #dcfce7; color: #166534; display: block; }
        .alert.error { background: #fee2e2; color: #991b1b; display: block; }

        /* Table */
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }
        .btn-refresh {
            background: #f1f5f9;
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            font-weight: 500;
        }
        .btn-refresh:hover { background: #e2e8f0; }
        .table-wrap {
            overflow-x: auto;
            max-height: 520px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th {
            text-align: left;
            padding: 10px 12px;
            background: #f8fafc;
            border-bottom: 1px solid var(--border);
            color: var(--text-muted);
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }
        tr:hover td { background: #fdfdfd; }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge.delivrd { background: #dcfce7; color: #15803d; }
        .badge.submitted { background: #fef3c7; color: #b45309; }
        .badge.failed { background: #fee2e2; color: #b91c1c; }
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>
                <span>📱</span> Nalo SMS Gateway
            </h1>
            <div class="header-links">
                <a href="/docs" target="_blank">Swagger API Docs</a>
                <a href="/api/config" target="_blank">Config Endpoint</a>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Sent</div>
                <div class="value" id="stat-total">0</div>
            </div>
            <div class="stat-card delivered">
                <div class="label">Delivered</div>
                <div class="value" id="stat-delivered">0</div>
            </div>
            <div class="stat-card pending">
                <div class="label">Pending</div>
                <div class="value" id="stat-pending">0</div>
            </div>
            <div class="stat-card failed">
                <div class="label">Failed</div>
                <div class="value" id="stat-failed">0</div>
            </div>
        </div>

        <div class="layout">
            <!-- Composer -->
            <div class="card">
                <h2>Send Message</h2>
                <form id="smsForm">
                    <div class="form-group">
                        <label for="senderId">Sender ID</label>
                        <select id="senderId" required>
                            <option value="">Loading Sender IDs...</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="numbers">Recipients</label>
                        <input type="text" id="numbers" placeholder="0244123456, 0551234567" required>
                        <div class="helper-text">Accepts 024XXXXXXX, 233XXXXXXXXX. Separate multiple with commas.</div>
                    </div>

                    <div class="form-group">
                        <label for="message">Message</label>
                        <textarea id="message" rows="5" placeholder="Type your SMS message..." required></textarea>
                        <div class="msg-meta">
                            <span><span id="charCount">0</span> chars</span>
                            <span><span id="smsParts">1</span> SMS part(s)</span>
                        </div>
                    </div>

                    <button type="submit" id="sendBtn" class="btn-primary">
                        <span>Send SMS</span>
                    </button>
                </form>
                <div id="alertBox" class="alert"></div>
            </div>

            <!-- Message History -->
            <div class="card">
                <div class="table-header">
                    <h2>Recent Messages</h2>
                    <button class="btn-refresh" id="refreshBtn">🔄 Refresh</button>
                </div>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Recipient</th>
                                <th>Message</th>
                                <th>Sender</th>
                                <th>Status</th>
                                <th>Sent</th>
                            </tr>
                        </thead>
                        <tbody id="messageTableBody">
                            <tr>
                                <td colspan="5" class="empty-state">Loading messages...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        const senderSelect = document.getElementById("senderId");
        const numbersInput = document.getElementById("numbers");
        const messageInput = document.getElementById("message");
        const charCount = document.getElementById("charCount");
        const smsParts = document.getElementById("smsParts");
        const sendBtn = document.getElementById("sendBtn");
        const alertBox = document.getElementById("alertBox");
        const refreshBtn = document.getElementById("refreshBtn");
        const tableBody = document.getElementById("messageTableBody");

        // Load configuration and Sender IDs
        async function loadConfig() {
            try {
                const res = await fetch("/api/config");
                const data = await res.json();
                senderSelect.innerHTML = "";
                if (data.senderIds && data.senderIds.length > 0) {
                    data.senderIds.forEach(id => {
                        const opt = document.createElement("option");
                        opt.value = id;
                        opt.textContent = id;
                        senderSelect.appendChild(opt);
                    });
                } else {
                    senderSelect.innerHTML = '<option value="Kelly">Kelly (Default)</option>';
                }
            } catch (err) {
                senderSelect.innerHTML = '<option value="Kelly">Kelly</option>';
            }
        }

        // Calculate character & segment count
        messageInput.addEventListener("input", () => {
            const len = messageInput.value.length;
            charCount.textContent = len;
            const parts = len <= 160 ? (len === 0 ? 1 : 1) : Math.ceil(len / 153);
            smsParts.textContent = parts;
        });

        // Load messages and stats
        async function loadMessages() {
            try {
                const res = await fetch("/api/messages");
                const data = await res.json();
                if (data.stats) {
                    document.getElementById("stat-total").textContent = data.stats.total;
                    document.getElementById("stat-delivered").textContent = data.stats.delivered;
                    document.getElementById("stat-pending").textContent = data.stats.pending;
                    document.getElementById("stat-failed").textContent = data.stats.failed;
                }
                if (!data.messages || data.messages.length === 0) {
                    tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">No messages sent yet.</td></tr>';
                    return;
                }
                tableBody.innerHTML = data.messages.map(m => {
                    const statusClass = m.status.toLowerCase().includes("deliv") ? "delivrd"
                                      : (m.status.toLowerCase().includes("fail") ? "failed" : "submitted");
                    const dateStr = m.sent_at ? new Date(m.sent_at).toLocaleTimeString() : "-";
                    const preview = m.message.length > 35 ? m.message.substring(0, 35) + "..." : m.message;
                    return `
                        <tr>
                            <td><strong>${m.recipient}</strong></td>
                            <td title="${m.message.replace(/"/g, '&quot;')}">${preview}</td>
                            <td>${m.sender_id}</td>
                            <td><span class="badge ${statusClass}">${m.status}</span></td>
                            <td style="color:#64748b; font-size:12px;">${dateStr}</td>
                        </tr>
                    `;
                }).join("");
            } catch (err) {
                tableBody.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load messages.</td></tr>';
            }
        }

        // Submit form
        document.getElementById("smsForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            alertBox.className = "alert";
            alertBox.style.display = "none";
            sendBtn.disabled = true;
            sendBtn.innerHTML = "<span>Sending...</span>";

            try {
                const payload = {
                    senderId: senderSelect.value,
                    numbers: numbersInput.value,
                    message: messageInput.value
                };
                const res = await fetch("/api/send", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                if (!res.ok) {
                    throw new Error(result.detail || "Failed to dispatch SMS.");
                }

                alertBox.className = "alert success";
                alertBox.textContent = `Success! Dispatched to ${result.results ? result.results.length : 1} recipient(s).`;
                messageInput.value = "";
                charCount.textContent = "0";
                smsParts.textContent = "1";
                await loadMessages();
            } catch (err) {
                alertBox.className = "alert error";
                alertBox.textContent = err.message || "An unexpected error occurred.";
            } finally {
                sendBtn.disabled = false;
                sendBtn.innerHTML = "<span>Send SMS</span>";
            }
        });

        refreshBtn.addEventListener("click", loadMessages);

        // Initial load and periodic polling
        loadConfig();
        loadMessages();
        setInterval(loadMessages, 5000);
    </script>
</body>
</html>"""

# ==========================================
# 5. API Endpoints
# ==========================================

@app.get("/api/config")
def get_config(request: Request):
    base_url = CALLBACK_BASE_URL
    if not base_url:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        proto = "https" if "https" in request.headers.get("x-forwarded-proto", "") else "http"
        base_url = f"{proto}://{host}" if host else "http://localhost:8000"

    return {
        "senderIds": SENDER_IDS,
        "callbackBaseUrl": base_url,
        "callbackEndpoint": f"{base_url}/api/callback",
        "hasApiKey": bool(SMS_API_KEY),
        "apiKeyPreview": f"{SMS_API_KEY[:4]}...{SMS_API_KEY[-4:]}" if SMS_API_KEY else None,
        "databaseEngine": "PostgreSQL" if "postgres" in DATABASE_URL else "SQLite",
    }


@app.post("/api/send")
async def send_sms(payload: SendSmsRequest, request: Request, db: Session = Depends(get_db)):
    # 1. Validation
    if SENDER_IDS and payload.senderId not in SENDER_IDS:
        raise HTTPException(status_code=400, detail=f"Sender ID '{payload.senderId}' is not allowed. Allowed: {', '.join(SENDER_IDS)}")

    raw_numbers = [n.strip() for n in payload.numbers.split(",") if n.strip()]
    valid_numbers = []
    invalid_numbers = []

    for num in raw_numbers:
        normalized = normalize_number(num)
        if normalized:
            valid_numbers.append(normalized)
        else:
            invalid_numbers.append(num)

    if invalid_numbers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Ghanaian number format: {', '.join(invalid_numbers)}. Use 024XXXXXXX or 233XXXXXXXXX."
        )

    if not valid_numbers:
        raise HTTPException(status_code=400, detail="No valid recipient numbers provided.")

    if not SMS_API_KEY:
        raise HTTPException(status_code=500, detail="SMS_API_KEY is missing from environment.")

    # 2. Resolve Callback URL
    callback_url = f"{CALLBACK_BASE_URL}/api/callback" if CALLBACK_BASE_URL else None
    if not callback_url:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host and "localhost" not in host and "127.0.0.1" not in host:
            callback_url = f"https://{host}/api/callback"

    # 3. Dispatch to Nalo Gateway
    results = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for recipient in valid_numbers:
            params = {
                "key": SMS_API_KEY,
                "type": "0",
                "dlr": "1",
                "destination": recipient,
                "source": payload.senderId,
                "message": payload.message,
            }
            if callback_url:
                params["callback_url"] = callback_url

            now_iso = datetime.now(timezone.utc).isoformat()

            try:
                resp = await client.get(NALO_ENDPOINT, params=params)
                resp_text = resp.text.strip()
                parts = [p.strip() for p in resp_text.split("|")]
                status_code = parts[0]

                if status_code == "1701":
                    # Format: 1701|destination|message_id
                    message_id = parts[2] if len(parts) >= 3 else parts[1]
                    msg_record = Message(
                        message_id=message_id,
                        sender_id=payload.senderId,
                        recipient=recipient,
                        message=payload.message,
                        status="SUBMITTED",
                        status_code="1701",
                        sent_at=now_iso,
                        raw_response=resp_text,
                    )
                    db.add(msg_record)
                    db.commit()
                    results.append({"recipient": recipient, "success": True, "messageId": message_id, "statusCode": "1701"})
                else:
                    clean_code = status_code.split(":")[0][:50]
                    msg_record = Message(
                        message_id=f"ERR-{int(datetime.now().timestamp())}",
                        sender_id=payload.senderId,
                        recipient=recipient,
                        message=payload.message,
                        status="FAILED",
                        status_code=clean_code,
                        sent_at=now_iso,
                        raw_response=resp_text,
                    )
                    db.add(msg_record)
                    db.commit()
                    results.append({"recipient": recipient, "success": False, "statusCode": clean_code, "error": resp_text})

            except Exception as exc:
                msg_record = Message(
                    message_id=f"ERR-{int(datetime.now().timestamp())}",
                    sender_id=payload.senderId,
                    recipient=recipient,
                    message=payload.message,
                    status="FAILED",
                    status_code="HTTP_ERROR",
                    sent_at=now_iso,
                    raw_response=str(exc),
                )
                db.add(msg_record)
                db.commit()
                results.append({"recipient": recipient, "success": False, "statusCode": "HTTP_ERROR", "error": str(exc)})

    all_success = all(r["success"] for r in results)
    return {
        "success": all_success,
        "message": "Messages processed by gateway.",
        "messageId": results[0]["messageId"] if results and "messageId" in results[0] else None,
        "senderId": payload.senderId,
        "results": results,
    }


@app.api_route("/api/callback", methods=["GET", "POST"])
async def receive_callback(request: Request, db: Session = Depends(get_db)):
    """Receives asynchronous Delivery Reports (DLR) from Nalo."""
    raw_body = await request.body()
    raw_text = raw_body.decode("utf-8", errors="ignore")

    data = dict(request.query_params)
    if raw_text:
        try:
            json_data = await request.json()
            if isinstance(json_data, dict):
                data.update(json_data)
        except Exception:
            import urllib.parse
            parsed_form = urllib.parse.parse_qs(raw_text)
            for k, v in parsed_form.items():
                data[k] = v[0] if v else ""

    def lookup(keys: list):
        for k in keys:
            if k in data and str(data[k]).strip():
                return str(data[k]).strip()
            for dk, dv in data.items():
                if dk.lower() == k.lower() and str(dv).strip():
                    return str(dv).strip()
        return None

    message_id = lookup(["mid", "message_id", "msg_id", "id", "batch_id"])
    raw_status = lookup(["status", "dlr_status", "delivery_status", "state"]) or "DELIVRD"
    status = parse_dlr_status(raw_status)
    status_code = (lookup(["status_code", "statusCode", "code"]) or "000")[:50]
    recipient = lookup(["msisdn", "destination", "to", "recipient", "phone"])

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Log in delivery_reports table
    report = DeliveryReport(
        message_id=message_id or f"DLR-{int(datetime.now().timestamp())}",
        recipient=recipient,
        status=status,
        status_code=status_code,
        received_at=now_iso,
        payload=raw_text or str(data),
    )
    db.add(report)

    # 2. Update message record (Exact match or fallback to last 9 digits of recipient)
    target_msg = None
    if message_id:
        target_msg = db.query(Message).filter(Message.message_id == message_id).first()

    if not target_msg and recipient:
        last9 = re.sub(r"\D", "", recipient)[-9:]
        target_msg = (
            db.query(Message)
            .filter(Message.recipient.like(f"%{last9}"), Message.status.in_(["SUBMITTED", "PENDING"]))
            .order_by(desc(Message.id))
            .first()
        )

    updated = False
    if target_msg:
        target_msg.status = status
        target_msg.status_code = status_code
        target_msg.delivered_at = now_iso
        target_msg.raw_callback = raw_text or str(data)
        updated = True

    db.commit()
    return {"success": True, "updated": updated, "messageId": message_id, "status": status}


@app.get("/api/messages")
def get_messages(db: Session = Depends(get_db)):
    """Fetches latest messages and delivery statistics with auto-reconciliation."""
    messages = db.query(Message).order_by(desc(Message.id)).limit(100).all()

    # Auto-reconciliation simulation for local development testing
    if AUTO_RECONCILE:
        now = datetime.now(timezone.utc).timestamp()
        dirty = False
        for msg in messages:
            if msg.status == "SUBMITTED":
                try:
                    sent_ts = datetime.fromisoformat(msg.sent_at.replace("Z", "+00:00")).timestamp()
                    if now - sent_ts >= 4.0:
                        msg.status = "DELIVRD"
                        msg.status_code = "000"
                        msg.delivered_at = datetime.now(timezone.utc).isoformat()
                        dirty = True
                except Exception:
                    pass
        if dirty:
            db.commit()

    total = len(messages)
    delivered = sum(1 for m in messages if m.status.upper() in ("DELIVRD", "DELIVERED"))
    failed = sum(1 for m in messages if m.status.upper() in ("FAILED", "UNDELIV", "REJECTD", "EXPIRED"))
    pending = max(0, total - delivered - failed)

    return {
        "success": True,
        "messages": [
            {
                "id": m.id,
                "message_id": m.message_id,
                "sender_id": m.sender_id,
                "recipient": m.recipient,
                "message": m.message,
                "status": m.status,
                "status_code": m.status_code,
                "sent_at": m.sent_at,
                "delivered_at": m.delivered_at,
                "raw_response": m.raw_response,
                "raw_callback": m.raw_callback,
            }
            for m in messages
        ],
        "stats": {
            "total": total,
            "delivered": delivered,
            "pending": pending,
            "failed": failed,
        },
    }

# ==========================================
# 6. Server Entrypoint
# ==========================================
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting SMS Gateway on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
