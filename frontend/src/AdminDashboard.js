import React, { useState, useEffect, useCallback } from "react";
import {
  adminGetPatients, adminGetPatient, adminDeletePatient,
  adminCreatePatient, adminUpdatePatient, adminGetStats,
  exportCSV, exportExcel, exportPDF,
  clearToken, saveToken
} from "./api";

const RISK_COLORS = {
  healthy:      "#16a34a",
  diabetes:     "#d97706",
  anaemia:      "#3b82f6",
  dyslipidaemia:"#9333ea",
  composite:    "#dc2626",
};
const RISK_LABELS = {
  healthy:"Healthy", diabetes:"Diabetes Risk", anaemia:"Anaemia Risk",
  dyslipidaemia:"Dyslipidaemia Risk", composite:"High Composite Risk"
};

function getRiskKey(remarks) {
  if (!remarks) return "healthy";
  const r = remarks.toLowerCase();
  if (r.includes("composite") || r.includes("multiple")) return "composite";
  if (r.includes("diabetes"))     return "diabetes";
  if (r.includes("anaemia"))      return "anaemia";
  if (r.includes("dyslipidaemia") || r.includes("cholesterol")) return "dyslipidaemia";
  return "healthy";
}

function DonutChart({ data }) {
  const total = Object.values(data).reduce((a,b) => a+b, 0) || 1;
  let offset = 0;
  const radius = 60, cx = 80, cy = 80, stroke = 28;
  const circumference = 2 * Math.PI * radius;
  const segments = Object.entries(data).filter(([,v]) => v > 0).map(([k, v]) => {
    const dash = (v / total) * circumference;
    const gap  = circumference - dash;
    const seg  = { key: k, color: RISK_COLORS[k], dash, gap, offset };
    offset += dash;
    return seg;
  });

  return (
    <div className="donut-wrap">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="#f0f4f9" strokeWidth={stroke} />
        {segments.map(s => (
          <circle key={s.key} cx={cx} cy={cy} r={radius} fill="none"
            stroke={s.color} strokeWidth={stroke}
            strokeDasharray={`${s.dash} ${s.gap}`}
            strokeDashoffset={-s.offset}
            style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
          />
        ))}
        <text x={cx} y={cy-6} textAnchor="middle" fontSize="22" fontWeight="800" fill="#1a2433">{total}</text>
        <text x={cx} y={cy+14} textAnchor="middle" fontSize="9" fill="#6b7d96">PATIENTS</text>
      </svg>
      <div className="donut-legend">
        {Object.entries(data).map(([k, v]) => (
          <div key={k} className="legend-item">
            <span className="legend-dot" style={{ background: RISK_COLORS[k] }} />
            <span>{RISK_LABELS[k]}</span>
            <span className="legend-val">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const EMPTY_FORM = { full_name:"", dob:"", email:"", glucose:"", haemoglobin:"", cholesterol:"" };

function PatientModal({ patient, onClose, onSaved, onError }) {
  const isNew = !patient || !patient.id;
  const [form, setForm] = useState(isNew ? EMPTY_FORM : {
    full_name: patient.full_name, dob: patient.dob, email: patient.email,
    glucose: String(patient.glucose||""), haemoglobin: String(patient.haemoglobin||""),
    cholesterol: String(patient.cholesterol||""),
  });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true); setFormError("");
    try {
      const payload = {
        full_name: form.full_name.trim(), dob: form.dob,
        email: form.email.trim().toLowerCase(),
        glucose: parseFloat(form.glucose),
        haemoglobin: parseFloat(form.haemoglobin),
        cholesterol: parseFloat(form.cholesterol),
      };
      if (isNew) await adminCreatePatient(payload);
      else await adminUpdatePatient(patient.id, payload);
      onSaved();
    } catch(err) {
      const msg = err?.errors?.join(" ") || err?.error || err?.message || "Failed to save. Check all fields.";
      setFormError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{isNew ? "Add New Patient" : "Edit Patient"}</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} noValidate className="modal-form">
          {formError && <div className="server-error" style={{marginBottom:"1rem"}}>{formError}</div>}
          {[
            {label:"Full Name",name:"full_name",type:"text"},
            {label:"Date of Birth",name:"dob",type:"date"},
            {label:"Email",name:"email",type:"email"},
            {label:"Glucose (mg/dL)",name:"glucose",type:"number"},
            {label:"Haemoglobin (g/dL)",name:"haemoglobin",type:"number"},
            {label:"Cholesterol (mg/dL)",name:"cholesterol",type:"number"},
          ].map(f => (
            <div className="field" key={f.name}>
              <label>{f.label}</label>
              <input type={f.type} value={form[f.name]}
                onChange={e => setForm(p => ({...p,[f.name]:e.target.value}))} />
            </div>
          ))}
          <div className="modal-actions">
            <button type="submit" className="btn btn--primary" disabled={busy}>
              {busy ? "Saving…" : "Save Patient"}
            </button>
            <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DetailPanel({ patientId, onClose }) {
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminGetPatient(patientId).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [patientId]);

  if (loading) return (
    <div className="detail-panel">
      <div className="loader"><span className="loader-dot"/><span className="loader-dot"/><span className="loader-dot"/></div>
    </div>
  );
  if (!data) return null;

  const rk    = getRiskKey(data.remarks);
  const color = RISK_COLORS[rk];
  const info  = data.condition_info || {};
  const NORMAL = { glucose:[70,100,"mg/dL"], haemoglobin:[12,17,"g/dL"], cholesterol:[0,200,"mg/dL"] };

  const handleExportPDF = () => exportPDF(data.id);

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <button className="detail-close" onClick={onClose}>← Back</button>
        <button className="btn btn--primary btn--sm" onClick={handleExportPDF}>⬇ PDF Report</button>
      </div>

      <div className="detail-patient-head">
        <div className="result-avatar" style={{ background: color + "20", color }}>{data.full_name?.charAt(0)}</div>
        <div>
          <h3>{data.full_name}</h3>
          <p className="result-meta">{data.email} · DOB: {data.dob}</p>
        </div>
        <span className="result-badge" style={{ background: color+"18", color, borderColor: color }}>
          {RISK_LABELS[rk]}
        </span>
      </div>

      <div className="detail-section">
        <h4>Blood Values</h4>
        {Object.entries(NORMAL).map(([key, [lo, hi, unit]]) => {
          const val = parseFloat(data[key]);
          const ok  = val >= lo && val <= hi;
          return (
            <div className="detail-value-row" key={key}>
              <span className="detail-value-label">{key.charAt(0).toUpperCase()+key.slice(1)}</span>
              <span className={`detail-value-num ${ok?"val--ok":"val--high"}`}>{val} {unit}</span>
              <span className="detail-value-range">Normal: {lo}–{hi}</span>
              <span className={`detail-value-status ${ok?"status--ok":"status--warn"}`}>{ok?"✓":"⚠"}</span>
            </div>
          );
        })}
      </div>

      <div className="detail-section">
        <h4>Condition</h4>
        <p className="detail-explanation">{info.how_it_happens}</p>
      </div>

      <div className="detail-section">
        <h4>Remedies</h4>
        <ul className="remedy-list">
          {(info.remedies||[]).map((r,i) => (
            <li key={i} className="remedy-item">
              <span className="remedy-num">{i+1}</span><span>{r}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="ai-warning ai-warning--sm">
        <span>⚠</span>
        <p>AI-generated result. Consult a qualified doctor before any medical decision.</p>
      </div>
    </div>
  );
}

export default function AdminDashboard({ username, onLogout }) {
  const [view,       setView]       = useState("dashboard"); // dashboard | patients
  const [stats,      setStats]      = useState(null);
  const [patients,   setPatients]   = useState([]);
  const [total,      setTotal]      = useState(0);
  const [page,       setPage]       = useState(1);
  const [search,     setSearch]     = useState("");
  const [riskFilter, setRiskFilter] = useState("all");
  const [detailId,   setDetailId]   = useState(null);
  const [modal,      setModal]      = useState(null); // null | "new" | patientObj
  const [toast,      setToast]      = useState(null);
  const [loading,    setLoading]    = useState(false);
  const PER_PAGE = 10;

  const showToast = useCallback((type, msg) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const d = await adminGetStats();
      setStats(d);
    } catch(err) {
      if (err?.error === "Unauthorized" || err?.error === "Token expired" || err?.error === "Invalid token") {
        clearToken(); onLogout();
      }
    }
  }, [onLogout]);

  const loadPatients = useCallback(async () => {
    setLoading(true);
    try {
      const d = await adminGetPatients({ page, per_page: PER_PAGE, search, risk: riskFilter });
      setPatients(d.patients);
      setTotal(d.total);
    } catch { showToast("error", "Failed to load patients."); }
    finally { setLoading(false); }
  }, [page, search, riskFilter, showToast]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { if (view === "patients") loadPatients(); }, [view, loadPatients]);

  const handleDelete = async (p) => {
    if (!window.confirm(`Delete "${p.full_name}"? This cannot be undone.`)) return;
    try {
      await adminDeletePatient(p.id);
      showToast("success", `${p.full_name} deleted.`);
      loadPatients(); loadStats();
      if (detailId === p.id) setDetailId(null);
    } catch { showToast("error", "Delete failed."); }
  };

  const handleExportCSV   = () => exportCSV();
  const handleExportExcel = () => exportExcel();

  const dist = stats?.risk_distribution || {};
  const recent = stats?.recent_patients || [];

  return (
    <div className="admin-shell">
      {/* Sidebar */}
      <aside className="admin-sidebar">
        <div className="sidebar-logo">
          <span className="logo-icon">⚕</span>
          <div>
            <div className="logo-title">MIRA</div>
            <div className="logo-sub">Admin Console</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          <button className={`sidebar-item ${view==="dashboard"?"sidebar-item--active":""}`} onClick={()=>setView("dashboard")}>
            <span>📊</span> Dashboard
          </button>
          <button className={`sidebar-item ${view==="patients"?"sidebar-item--active":""}`} onClick={()=>setView("patients")}>
            <span>🗂</span> Patient Records
          </button>
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">👤 {username}</div>
          <button className="sidebar-logout" onClick={() => { clearToken(); onLogout(); }}>Sign Out</button>
        </div>
      </aside>

      {/* Main */}
      <div className="admin-main">
        {/* Toast */}
        {toast && (
          <div className={`toast toast--${toast.type}`}>
            <span>{toast.type==="success"?"✓":"✕"}</span> {toast.msg}
          </div>
        )}

        {/* Dashboard View */}
        {view === "dashboard" && (
          <div className="admin-content">
            <div className="admin-page-header">
              <h2>Dashboard</h2>
              <p>Overview of all patient health predictions</p>
            </div>

            <div className="stat-cards">
              <div className="stat-card">
                <div className="stat-num">{stats?.total_patients ?? "—"}</div>
                <div className="stat-label">Total Patients</div>
              </div>
              {Object.entries(dist).filter(([,v])=>v>0).map(([k,v])=>(
                <div className="stat-card" key={k} style={{ borderTop: `3px solid ${RISK_COLORS[k]}` }}>
                  <div className="stat-num" style={{ color: RISK_COLORS[k] }}>{v}</div>
                  <div className="stat-label">{RISK_LABELS[k]}</div>
                </div>
              ))}
            </div>

            <div className="dashboard-grid">
              <div className="dash-panel">
                <h3 className="dash-panel-title">Risk Distribution</h3>
                {stats ? <DonutChart data={dist} /> : <div className="loader-mini">Loading…</div>}
              </div>
              <div className="dash-panel">
                <h3 className="dash-panel-title">Recent Patients</h3>
                <div className="recent-list">
                  {recent.map(p => {
                    const rk = getRiskKey(p.remarks);
                    const color = RISK_COLORS[rk];
                    return (
                      <div className="recent-item" key={p.id}
                        onClick={() => { setView("patients"); setTimeout(()=>setDetailId(p.id),100); }}>
                        <div className="recent-avatar" style={{ background: color+"20", color }}>
                          {p.full_name?.charAt(0)}
                        </div>
                        <div className="recent-info">
                          <div className="recent-name">{p.full_name}</div>
                          <div className="recent-meta">{p.email}</div>
                        </div>
                        <span className="mini-badge" style={{ background: color+"18", color, borderColor: color }}>
                          {RISK_LABELS[rk]}
                        </span>
                      </div>
                    );
                  })}
                  {recent.length === 0 && <p className="muted">No patients yet.</p>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Patients View */}
        {view === "patients" && (
          <div className="admin-content admin-content--split">
            <div className={`patients-panel ${detailId ? "patients-panel--narrow" : ""}`}>
              <div className="admin-page-header">
                <div>
                  <h2>Patient Records</h2>
                  <p>{total} total records</p>
                </div>
                <div className="header-actions">
                  <button className="btn btn--primary btn--sm" onClick={() => setModal("new")}>+ Add Patient</button>
                  <button className="btn btn--ghost btn--sm" onClick={handleExportCSV}>⬇ CSV</button>
                  <button className="btn btn--ghost btn--sm" onClick={handleExportExcel}>⬇ Excel</button>
                </div>
              </div>

              {/* Filters */}
              <div className="filter-bar">
                <input className="search-input" type="search" placeholder="Search name or email…"
                  value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
                <select className="risk-select" value={riskFilter}
                  onChange={e => { setRiskFilter(e.target.value); setPage(1); }}>
                  <option value="all">All Conditions</option>
                  <option value="healthy">Healthy</option>
                  <option value="diabetes">Diabetes Risk</option>
                  <option value="anaemia">Anaemia Risk</option>
                  <option value="dyslipidaemia">Dyslipidaemia Risk</option>
                  <option value="composite">High Composite Risk</option>
                </select>
              </div>

              {/* Table */}
              {loading ? (
                <div className="loader"><span className="loader-dot"/><span className="loader-dot"/><span className="loader-dot"/> Loading…</div>
              ) : (
                <div className="table-scroll">
                  <table className="patient-table">
                    <thead>
                      <tr>
                        <th>#</th><th>Name</th><th>DOB</th><th>Email</th>
                        <th>Glucose</th><th>Hb</th><th>Chol.</th><th>Condition</th><th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {patients.map((p,i) => {
                        const rk = getRiskKey(p.remarks);
                        const color = RISK_COLORS[rk];
                        return (
                          <tr key={p.id} className={`patient-row ${detailId===p.id?"patient-row--active":""}`}
                            onClick={() => setDetailId(detailId===p.id ? null : p.id)} style={{cursor:"pointer"}}>
                            <td>{(page-1)*PER_PAGE+i+1}</td>
                            <td><strong>{p.full_name}</strong></td>
                            <td>{p.dob}</td>
                            <td className="email-cell">{p.email}</td>
                            <td>{p.glucose}</td><td>{p.haemoglobin}</td><td>{p.cholesterol}</td>
                            <td>
                              <span className="risk-badge" style={{ borderColor: color, color }}>
                                {RISK_LABELS[rk]}
                              </span>
                            </td>
                            <td className="action-cell" onClick={e => e.stopPropagation()}>
                              <button className="icon-btn icon-btn--edit"
                                onClick={() => setModal(p)} title="Edit">✎</button>
                              <button className="icon-btn icon-btn--delete"
                                onClick={() => handleDelete(p)} title="Delete">✕</button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {patients.length === 0 && (
                    <div className="empty-state"><span>🩺</span><p>No records found.</p></div>
                  )}
                </div>
              )}

              {/* Pagination */}
              {total > PER_PAGE && (
                <div className="pagination">
                  <button className="page-btn" disabled={page===1} onClick={()=>setPage(p=>p-1)}>← Prev</button>
                  <span className="page-info">Page {page} of {Math.ceil(total/PER_PAGE)}</span>
                  <button className="page-btn" disabled={page>=Math.ceil(total/PER_PAGE)} onClick={()=>setPage(p=>p+1)}>Next →</button>
                </div>
              )}
            </div>

            {/* Detail Panel */}
            {detailId && (
              <DetailPanel patientId={detailId} onClose={() => setDetailId(null)} />
            )}
          </div>
        )}
      </div>

      {/* Modal */}
      {modal && (
        <PatientModal
          patient={modal === "new" ? null : modal}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); loadPatients(); loadStats(); showToast("success", "Patient saved."); }}
          onError={msg => showToast("error", msg)}
        />
      )}
    </div>
  );
}
