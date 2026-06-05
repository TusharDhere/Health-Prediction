"""
app.py – MIRA Health Platform (Upgraded)
========================================
Endpoints (public):
  GET    /health
  GET    /patients/recent        – most recent patient (for patient-facing UI)
  POST   /patients               – create patient + run ML prediction

Endpoints (admin – JWT required):
  POST   /admin/login
  GET    /admin/patients         – paginated, search, filter
  GET    /admin/patients/<id>
  PUT    /admin/patients/<id>
  DELETE /admin/patients/<id>
  GET    /admin/stats            – dashboard stats
  GET    /admin/export/csv       – all records as CSV
  GET    /admin/export/excel     – all records as Excel
  GET    /admin/export/pdf/<id>  – single patient PDF report
"""

from flask import Flask, request, jsonify, send_from_directory, make_response
import os, re, json, io, csv
from datetime import date, datetime, timezone, timedelta

import joblib
import numpy as np
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import jwt
import bcrypt

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
FRONTEND_BUILD  = os.path.join(BASE_DIR, "..", "frontend", "build")
# On Render use /data (persistent disk); locally fall back to backend dir
DATA_DIR        = os.environ.get("DATA_DIR", BASE_DIR)
DB_PATH         = os.path.join(DATA_DIR, "mira.db")

app = Flask(
    __name__,
    static_folder=FRONTEND_BUILD,
    static_url_path=""
)
CORS(app)

# ── Config ─────────────────────────────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"]        = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
JWT_SECRET  = os.environ.get("JWT_SECRET", "mira-health-platform-jwt-secret-key-2025-production-secure-64chars!!")
JWT_EXPIRY  = 8   # hours

db = SQLAlchemy(app)

# ── ORM Models ─────────────────────────────────────────────────────────────────
class Patient(db.Model):
    __tablename__ = "patients"
    id          = db.Column(db.Integer,     primary_key=True)
    full_name   = db.Column(db.String(120), nullable=False)
    dob         = db.Column(db.String(20),  nullable=False)
    email       = db.Column(db.String(160), nullable=False, unique=True)
    created_at  = db.Column(db.DateTime,    default=datetime.utcnow)
    records     = db.relationship("HealthRecord", backref="patient", cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        latest = HealthRecord.query.filter_by(patient_id=self.id).order_by(HealthRecord.id.desc()).first()
        return {
            "id":          self.id,
            "full_name":   self.full_name,
            "dob":         self.dob,
            "email":       self.email,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
            "glucose":     latest.glucose     if latest else None,
            "haemoglobin": latest.haemoglobin if latest else None,
            "cholesterol": latest.cholesterol if latest else None,
            "remarks":     latest.remarks     if latest else "",
            "predicted_at":latest.predicted_at.isoformat() if latest and latest.predicted_at else None,
        }


class HealthRecord(db.Model):
    __tablename__ = "health_records"
    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    glucose      = db.Column(db.Float,   nullable=False)
    haemoglobin  = db.Column(db.Float,   nullable=False)
    cholesterol  = db.Column(db.Float,   nullable=False)
    remarks      = db.Column(db.Text,    nullable=True)
    predicted_at = db.Column(db.DateTime, default=datetime.utcnow)


class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id            = db.Column(db.Integer,     primary_key=True)
    username      = db.Column(db.String(80),  nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)


# ── ML Prediction ──────────────────────────────────────────────────────────────
_MODEL = _FEATURES = _LABEL_MAP = None

def _load_model():
    global _MODEL, _FEATURES, _LABEL_MAP
    if _MODEL is not None:
        return _MODEL
    model_path    = os.path.join(BASE_DIR, "model.pkl")
    features_path = os.path.join(BASE_DIR, "features.json")
    if os.path.exists(model_path):
        _MODEL = joblib.load(model_path)
        if os.path.exists(features_path):
            with open(features_path) as f:
                meta = json.load(f)
            _FEATURES  = meta.get("features", [])
            _LABEL_MAP = {int(k): v for k, v in meta.get("labels", {}).items()}
        return _MODEL
    return None

def _build_feature_vector(g, hb, ch):
    ghr  = g  / (hb + 1e-6)
    chr_ = ch / (hb + 1e-6)
    gn   = (g  - 85)  / 30
    hbn  = (hb - 14.5) / 2.5
    chn  = (ch - 160)  / 40
    crs  = int(g > 140) + int(hb < 12) + int(ch > 200)
    return np.array([[g, hb, ch, ghr, chr_, gn, hbn, chn, crs]])

def _rule_based(g, hb, ch):
    issues = []
    if g  > 140: issues.append("Diabetes Risk")
    if hb < 12:  issues.append("Anaemia Risk")
    if ch > 200: issues.append("Dyslipidaemia Risk")
    if not issues: return "Healthy – all values within normal range."
    if len(issues) >= 2: return "High Composite Risk – multiple abnormal values detected."
    return issues[0] + " – elevated values detected."

def predict_health(g, hb, ch):
    model = _load_model()
    if model and _LABEL_MAP:
        try:
            X    = _build_feature_vector(g, hb, ch)
            pred = int(model.predict(X)[0])
            prob = model.predict_proba(X)[0]
            conf = round(float(prob[pred]) * 100, 1)
            label = _LABEL_MAP.get(pred, "Risk detected.")
            return f"{label} (Confidence: {conf}%)"
        except Exception as e:
            print(f"Model error: {e}")
    return _rule_based(g, hb, ch)

# ── JWT Auth ───────────────────────────────────────────────────────────────────
def make_token(user_id):
    payload = {
        "sub": str(user_id),  # PyJWT requires sub to be a string
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            print(f"[AUTH] No Bearer token on {request.path}")
            return jsonify({"error": "Unauthorized"}), 401
        token = auth[7:].strip()
        if not token:
            print(f"[AUTH] Empty token on {request.path}")
            return jsonify({"error": "Unauthorized"}), 401
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            print(f"[AUTH] Expired token on {request.path}")
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            print(f"[AUTH] Invalid token on {request.path}: {e}")
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return wrapper

# ── Validation ─────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def parse_dob(raw):
    """Accept DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD etc. Returns (date_obj, 'YYYY-MM-DD')."""
    raw = str(raw).strip()
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%y"]:
        try:
            d = datetime.strptime(raw, fmt).date()
            return d, d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {raw}")

def validate_patient(data, partial=False):
    errors = []
    if not partial:
        for f in ["full_name","dob","email","glucose","haemoglobin","cholesterol"]:
            if f not in data or str(data.get(f,"")).strip() == "":
                errors.append(f"'{f}' is required.")
    if "full_name" in data and data["full_name"] and len(str(data["full_name"]).strip()) < 2:
        errors.append("Full name must be at least 2 characters.")
    if "email" in data and data["email"] and not EMAIL_RE.match(str(data["email"])):
        errors.append("Invalid email address.")
    if "dob" in data and data["dob"]:
        try:
            dob_date, normalised = parse_dob(data["dob"])
            if dob_date >= date.today():
                errors.append("DOB cannot be today or a future date.")
            else:
                data["dob"] = normalised   # normalise to YYYY-MM-DD in-place
        except ValueError as e:
            errors.append(f"Invalid date — use YYYY-MM-DD or DD-MM-YYYY. ({e})")
    for field in ["glucose","haemoglobin","cholesterol"]:
        if field in data and data[field] not in ("", None):
            try:
                if float(data[field]) < 0:
                    errors.append(f"'{field}' must be positive.")
            except (TypeError, ValueError):
                errors.append(f"'{field}' must be numeric.")
    return errors

# ── Health condition metadata ──────────────────────────────────────────────────
CONDITION_INFO = {
    "healthy": {
        "label": "Healthy",
        "color": "#16a34a",
        "how_it_happens": "All your blood values — glucose, haemoglobin, and cholesterol — are within healthy ranges. Your body is effectively managing blood sugar, oxygen transport, and fat metabolism.",
        "remedies": [
            "Maintain a balanced diet rich in fruits, vegetables, and whole grains",
            "Exercise at least 30 minutes a day, 5 days a week",
            "Stay hydrated — aim for 8 glasses of water daily",
            "Get 7–8 hours of quality sleep every night",
            "Schedule annual blood work to stay on track"
        ]
    },
    "diabetes": {
        "label": "Diabetes Risk",
        "color": "#d97706",
        "how_it_happens": "Your glucose level is elevated. Diabetes occurs when the body cannot produce enough insulin or use it effectively, causing sugar to build up in the bloodstream instead of entering cells for energy.",
        "remedies": [
            "Reduce refined sugar and processed carbohydrate intake significantly",
            "Walk or exercise for at least 30 minutes daily to improve insulin sensitivity",
            "Eat smaller, more frequent meals to stabilize blood sugar spikes",
            "Increase fiber intake through vegetables, legumes, and whole grains",
            "Avoid sugary drinks — replace with water, herbal tea, or buttermilk"
        ]
    },
    "anaemia": {
        "label": "Anaemia Risk",
        "color": "#3b82f6",
        "how_it_happens": "Your haemoglobin is lower than normal. Anaemia occurs when your blood doesn't have enough healthy red blood cells to carry adequate oxygen to your body's tissues, causing fatigue and weakness.",
        "remedies": [
            "Eat iron-rich foods: spinach, lentils, beans, red meat, and fortified cereals",
            "Pair iron-rich foods with Vitamin C (lemon, orange) to boost iron absorption",
            "Avoid tea or coffee immediately after meals as they inhibit iron absorption",
            "Include Vitamin B12 sources: eggs, dairy, fish, and meat in your diet",
            "Cook in cast iron cookware — it naturally adds iron to food"
        ]
    },
    "dyslipidaemia": {
        "label": "Dyslipidaemia Risk",
        "color": "#9333ea",
        "how_it_happens": "Your cholesterol is elevated. Dyslipidaemia means abnormal fat levels in the blood. High cholesterol can build up in artery walls, narrowing them and increasing risk of heart disease or stroke over time.",
        "remedies": [
            "Eliminate trans fats and limit saturated fats found in fried and processed food",
            "Eat heart-healthy fats: avocado, nuts, olive oil, and fatty fish like salmon",
            "Add soluble fiber: oats, barley, apples, and flaxseed lower LDL cholesterol",
            "Exercise regularly — aerobic activity raises good HDL cholesterol",
            "Quit smoking if applicable — it significantly raises bad cholesterol levels"
        ]
    },
    "composite": {
        "label": "High Composite Risk",
        "color": "#dc2626",
        "how_it_happens": "Multiple blood values are outside the healthy range. This means your body is simultaneously dealing with more than one metabolic issue — such as high blood sugar, low haemoglobin, and high cholesterol together — which compounds overall health risk.",
        "remedies": [
            "Consult a doctor immediately — multiple risks require coordinated medical care",
            "Follow a whole-food diet eliminating sugar, processed food, and trans fats",
            "Begin a supervised exercise program — even light daily walking helps",
            "Prioritize sleep and stress management — both worsen metabolic conditions",
            "Track your values monthly and maintain a health diary for your doctor"
        ]
    }
}

def get_condition_key(remarks):
    if not remarks: return "healthy"
    r = remarks.lower()
    if "composite" in r or "multiple" in r: return "composite"
    if "diabetes"  in r: return "diabetes"
    if "anaemia"   in r: return "anaemia"
    if "dyslipidaemia" in r or "cholesterol" in r: return "dyslipidaemia"
    return "healthy"

# ── Static / SPA Routes ────────────────────────────────────────────────────────
@app.route("/")
def serve():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/admin")
def serve_admin():
    """Serve the React SPA for the /admin frontend route."""
    return send_from_directory(app.static_folder, "index.html")

@app.route("/static/<path:path>")
def serve_static(path):
    """Serve React's compiled static assets (js/css/media)."""
    return send_from_directory(os.path.join(app.static_folder, "static"), path)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "MIRA API is running."})

@app.route("/patients/recent", methods=["GET"])
def get_recent_patient():
    """Returns the most recently added patient with full health info."""
    latest_record = HealthRecord.query.order_by(HealthRecord.id.desc()).first()
    if not latest_record:
        return jsonify(None)
    p = Patient.query.get(latest_record.patient_id)
    condition_key = get_condition_key(latest_record.remarks)
    info = CONDITION_INFO.get(condition_key, CONDITION_INFO["healthy"])
    return jsonify({
        "id":           p.id,
        "full_name":    p.full_name,
        "dob":          p.dob,
        "email":        p.email,
        "glucose":      latest_record.glucose,
        "haemoglobin":  latest_record.haemoglobin,
        "cholesterol":  latest_record.cholesterol,
        "remarks":      latest_record.remarks,
        "predicted_at": latest_record.predicted_at.isoformat() if latest_record.predicted_at else None,
        "condition_key": condition_key,
        "condition_info": info,
    })

@app.route("/patients", methods=["POST"])
def create_patient():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"errors": ["Request body must be JSON."]}), 400
    errors = validate_patient(data)
    if errors:
        return jsonify({"errors": errors}), 422

    email = data["email"].strip().lower()
    existing = Patient.query.filter_by(email=email).first()

    g   = float(data["glucose"])
    hb  = float(data["haemoglobin"])
    ch  = float(data["cholesterol"])
    remarks = predict_health(g, hb, ch)

    if existing:
        # Update existing patient with new health record
        patient = existing
        patient.full_name = data["full_name"].strip()
        patient.dob       = data["dob"]
    else:
        patient = Patient(
            full_name = data["full_name"].strip(),
            dob       = data["dob"],
            email     = email,
        )
        db.session.add(patient)
        db.session.flush()

    record = HealthRecord(
        patient_id  = patient.id,
        glucose     = g,
        haemoglobin = hb,
        cholesterol = ch,
        remarks     = remarks,
    )
    db.session.add(record)
    db.session.commit()

    condition_key = get_condition_key(remarks)
    info = CONDITION_INFO.get(condition_key, CONDITION_INFO["healthy"])
    return jsonify({
        "id":             patient.id,
        "full_name":      patient.full_name,
        "dob":            patient.dob,
        "email":          patient.email,
        "glucose":        g,
        "haemoglobin":    hb,
        "cholesterol":    ch,
        "remarks":        remarks,
        "condition_key":  condition_key,
        "condition_info": info,
    }), 201

# ── Admin Auth ─────────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username","").strip()
    password = data.get("password","").encode()
    user = AdminUser.query.filter_by(username=username).first()
    if not user or not bcrypt.checkpw(password, user.password_hash.encode()):
        return jsonify({"error": "Invalid username or password."}), 401
    token = make_token(user.id)
    return jsonify({"token": token, "username": user.username})

# ── Admin Patient CRUD ─────────────────────────────────────────────────────────
@app.route("/admin/patients", methods=["GET"])
@require_auth
def admin_get_patients():
    page    = int(request.args.get("page", 1))
    per_page= int(request.args.get("per_page", 10))
    search  = request.args.get("search","").strip()
    risk    = request.args.get("risk","").strip().lower()

    query = Patient.query
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Patient.full_name.ilike(like), Patient.email.ilike(like))
        )

    patients = query.order_by(Patient.id.desc()).all()
    result = [p.to_dict() for p in patients]

    if risk and risk != "all":
        result = [r for r in result if risk in (r.get("remarks") or "").lower()]

    total = len(result)
    start = (page - 1) * per_page
    paged = result[start:start + per_page]
    return jsonify({"patients": paged, "total": total, "page": page, "per_page": per_page})

@app.route("/admin/patients/<int:pid>", methods=["GET"])
@require_auth
def admin_get_patient(pid):
    p = Patient.query.get_or_404(pid)
    d = p.to_dict()
    condition_key = get_condition_key(d.get("remarks",""))
    d["condition_info"] = CONDITION_INFO.get(condition_key, CONDITION_INFO["healthy"])
    d["condition_key"]  = condition_key
    return jsonify(d)

@app.route("/admin/patients/<int:pid>", methods=["PUT"])
@require_auth
def admin_update_patient(pid):
    patient = Patient.query.get_or_404(pid)
    data    = request.get_json(silent=True) or {}
    errors  = validate_patient(data, partial=True)
    if errors: return jsonify({"errors": errors}), 422

    if "email" in data:
        new_email = data["email"].strip().lower()
        existing  = Patient.query.filter_by(email=new_email).first()
        if existing and existing.id != pid:
            return jsonify({"errors": ["Another patient uses this email."]}), 409
        patient.email = new_email
    if "full_name" in data: patient.full_name = data["full_name"].strip()
    if "dob"       in data: patient.dob       = data["dob"]

    g  = float(data.get("glucose",     HealthRecord.query.filter_by(patient_id=pid).order_by(HealthRecord.id.desc()).first().glucose))
    hb = float(data.get("haemoglobin", HealthRecord.query.filter_by(patient_id=pid).order_by(HealthRecord.id.desc()).first().haemoglobin))
    ch = float(data.get("cholesterol", HealthRecord.query.filter_by(patient_id=pid).order_by(HealthRecord.id.desc()).first().cholesterol))

    if any(k in data for k in ["glucose","haemoglobin","cholesterol"]):
        remarks = predict_health(g, hb, ch)
        record = HealthRecord(patient_id=pid, glucose=g, haemoglobin=hb, cholesterol=ch, remarks=remarks)
        db.session.add(record)

    db.session.commit()
    return jsonify(Patient.query.get(pid).to_dict())

@app.route("/admin/patients/<int:pid>", methods=["DELETE"])
@require_auth
def admin_delete_patient(pid):
    patient = Patient.query.get_or_404(pid)
    name = patient.full_name
    db.session.delete(patient)
    db.session.commit()
    return jsonify({"message": f"Patient '{name}' deleted."})

@app.route("/admin/patients", methods=["POST"])
@require_auth
def admin_create_patient():
    return create_patient()

# ── Admin Stats ────────────────────────────────────────────────────────────────
@app.route("/admin/stats", methods=["GET"])
@require_auth
def admin_stats():
    total = Patient.query.count()
    recent = []
    for p in Patient.query.order_by(Patient.id.desc()).limit(5).all():
        d = p.to_dict()
        recent.append(d)

    all_records = HealthRecord.query.all()
    dist = {"healthy": 0, "diabetes": 0, "anaemia": 0, "dyslipidaemia": 0, "composite": 0}
    for r in all_records:
        k = get_condition_key(r.remarks)
        dist[k] = dist.get(k, 0) + 1

    return jsonify({"total_patients": total, "risk_distribution": dist, "recent_patients": recent})

# ── Admin Export ───────────────────────────────────────────────────────────────
@app.route("/admin/export/csv", methods=["GET"])
@require_auth
def export_csv():
    patients = Patient.query.order_by(Patient.id).all()
    output   = io.StringIO()
    writer   = csv.writer(output)
    writer.writerow(["ID","Full Name","DOB","Email","Glucose (mg/dL)","Haemoglobin (g/dL)","Cholesterol (mg/dL)","AI Prediction","Created At"])
    for p in patients:
        d = p.to_dict()
        writer.writerow([d["id"],d["full_name"],d["dob"],d["email"],d["glucose"],d["haemoglobin"],d["cholesterol"],d["remarks"],d["created_at"]])
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"]        = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=mira_patients.csv"
    return resp

@app.route("/admin/export/excel", methods=["GET"])
@require_auth
def export_excel():
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return jsonify({"error": "openpyxl not installed. Run: pip install openpyxl"}), 500

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MIRA Patient Records"

    headers = ["ID","Full Name","DOB","Email","Glucose (mg/dL)","Haemoglobin (g/dL)","Cholesterol (mg/dL)","AI Prediction","Created At"]
    header_fill = PatternFill("solid", fgColor="0F1E35")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal="center")

    for p in Patient.query.order_by(Patient.id).all():
        d = p.to_dict()
        ws.append([d["id"],d["full_name"],d["dob"],d["email"],d["glucose"],d["haemoglobin"],d["cholesterol"],d["remarks"],d["created_at"]])

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 20

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers["Content-Type"]        = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = "attachment; filename=mira_patients.xlsx"
    return resp

@app.route("/admin/export/pdf/<int:pid>", methods=["GET"])
@require_auth
def export_pdf(pid):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import cm
    except ImportError:
        return jsonify({"error": "reportlab not installed. Run: pip install reportlab"}), 500

    patient = Patient.query.get_or_404(pid)
    d = patient.to_dict()
    condition_key = get_condition_key(d.get("remarks",""))
    info = CONDITION_INFO.get(condition_key, CONDITION_INFO["healthy"])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    navy  = colors.HexColor("#0F1E35")
    blue  = colors.HexColor("#2563eb")
    amber = colors.HexColor("#d97706")

    title_style   = ParagraphStyle("Title",  fontSize=22, textColor=navy,  fontName="Helvetica-Bold", spaceAfter=4)
    sub_style     = ParagraphStyle("Sub",    fontSize=10, textColor=colors.HexColor("#6b7d96"), spaceAfter=12)
    heading_style = ParagraphStyle("H2",     fontSize=13, textColor=navy,  fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)
    body_style    = ParagraphStyle("Body",   fontSize=10, textColor=colors.HexColor("#1a2433"), leading=16)
    warn_style    = ParagraphStyle("Warn",   fontSize=9,  textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fffbeb"), borderPadding=8, leading=14)
    bullet_style  = ParagraphStyle("Bullet", fontSize=10, textColor=colors.HexColor("#1a2433"), leading=18, leftIndent=12)

    story = []
    story.append(Paragraph("⚕ MIRA Health Report", title_style))
    story.append(Paragraph("Medical Intelligence &amp; Risk Assessment — Patient Health Summary", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=blue))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Patient Information", heading_style))
    info_data = [
        ["Full Name",   d["full_name"]],
        ["Date of Birth", d["dob"]],
        ["Email",       d["email"]],
        ["Report Date", datetime.now().strftime("%d %B %Y")],
    ]
    t = Table(info_data, colWidths=[4.5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f0f4f9")),
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#dde4ef")),
        ("PADDING",    (0,0), (-1,-1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Blood Test Results", heading_style))
    NORMAL = {"Glucose": "70–100 mg/dL", "Haemoglobin": "12–17 g/dL", "Cholesterol": "<200 mg/dL"}
    val_data = [["Parameter","Your Value","Normal Range","Status"]]
    vals = [("Glucose", d["glucose"], "mg/dL", 70, 140), ("Haemoglobin", d["haemoglobin"], "g/dL", 12, 17), ("Cholesterol", d["cholesterol"], "mg/dL", 0, 200)]
    for name, val, unit, lo, hi in vals:
        status = "✓ Normal" if lo <= float(val) <= hi else "⚠ Abnormal"
        val_data.append([name, f"{val} {unit}", NORMAL[name], status])
    vt = Table(val_data, colWidths=[4.5*cm, 4*cm, 4*cm, 4*cm])
    vt.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), navy),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f8fafc"),colors.white]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#dde4ef")),
        ("PADDING",     (0,0), (-1,-1), 8),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
    ]))
    story.append(vt)
    story.append(Spacer(1, 14))

    story.append(Paragraph("AI Health Prediction", heading_style))
    story.append(Paragraph(f"<b>Condition:</b> {info['label']}", body_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>How it happens:</b> {info['how_it_happens']}", body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Recommended Remedies &amp; Lifestyle Tips:", ParagraphStyle("BH", fontSize=10, fontName="Helvetica-Bold", textColor=navy, spaceBefore=4, spaceAfter=4)))
    for remedy in info["remedies"]:
        story.append(Paragraph(f"• {remedy}", bullet_style))
    story.append(Spacer(1, 14))

    story.append(HRFlowable(width="100%", thickness=1, color=amber))
    story.append(Spacer(1, 6))
    warning_text = "⚠ AI DISCLAIMER: This report is generated by an AI/ML model and is intended for informational purposes only. It is NOT a substitute for professional medical advice, diagnosis, or treatment. Please consult a qualified physician before making any health decisions."
    story.append(Paragraph(warning_text, warn_style))

    doc.build(story)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers["Content-Type"]        = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename=mira_report_{pid}.pdf"
    return resp

# ── DB Init & Seed Admin ───────────────────────────────────────────────────────
def seed_admin():
    try:
        if not AdminUser.query.filter_by(username="admin").first():
            pw_hash = bcrypt.hashpw(b"Mohini123", bcrypt.gensalt()).decode()
            admin = AdminUser(username="administrator", password_hash=pw_hash)
            db.session.add(admin)
            db.session.commit()
    except Exception:
        db.session.rollback()   # another worker already inserted — safe to ignore

# ── Always runs — works with both gunicorn and `python app.py` ─────────────────
with app.app_context():
    os.makedirs(DATA_DIR, exist_ok=True)
    db.create_all()
    seed_admin()
    print(f"✅ Database ready at {DB_PATH}")

_load_model()

if __name__ == "__main__":
    print("🚀 MIRA backend running at http://localhost:5000")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
