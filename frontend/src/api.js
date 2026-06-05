/**
 * api.js – MIRA API helpers
 */
const BASE = process.env.REACT_APP_API_URL || "";

function getToken() {
  return localStorage.getItem("mira_token") || "";
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch (networkErr) {
    throw { error: "Network error — server may be down." };
  }

  if (res.status === 204) return null;
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw json;
  return json;
}

// Public
export const createPatient      = (body) => request("/patients", { method: "POST", body: JSON.stringify(body) });
export const fetchRecentPatient = ()     => request("/patients/recent");

// Admin auth
export const adminLogin         = (body) => request("/admin/login", { method: "POST", body: JSON.stringify(body) });

// Admin patients
export const adminGetPatients   = (params) => request(`/admin/patients?${new URLSearchParams(params)}`);
export const adminGetPatient    = (id)     => request(`/admin/patients/${id}`);
export const adminCreatePatient = (body)   => request("/admin/patients", { method: "POST", body: JSON.stringify(body) });
export const adminUpdatePatient = (id, b)  => request(`/admin/patients/${id}`, { method: "PUT", body: JSON.stringify(b) });
export const adminDeletePatient = (id)     => request(`/admin/patients/${id}`, { method: "DELETE" });

// Admin stats & exports
export const adminGetStats = () => request("/admin/stats");

function downloadWithAuth(url, filename) {
  return fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then(r => r.blob())
    .then(blob => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    });
}

export const exportCSV   = ()   => downloadWithAuth(`${BASE}/admin/export/csv`,       "mira_patients.csv");
export const exportExcel = ()   => downloadWithAuth(`${BASE}/admin/export/excel`,     "mira_patients.xlsx");
export const exportPDF   = (id) => downloadWithAuth(`${BASE}/admin/export/pdf/${id}`, `mira_report_${id}.pdf`);

// Auth helpers
export const saveToken  = (t) => localStorage.setItem("mira_token", t);
export const clearToken = ()  => { localStorage.removeItem("mira_token"); localStorage.removeItem("mira_username"); };
export const isLoggedIn = ()  => !!localStorage.getItem("mira_token");
