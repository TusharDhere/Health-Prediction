import React, { useState } from "react";
import { adminLogin, saveToken } from "./api";

export default function AdminLogin({ onLogin }) {
  const [form, setForm]   = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy]   = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.username || !form.password) { setError("Both fields are required."); return; }
    setBusy(true); setError("");
    try {
      const data = await adminLogin(form);
      saveToken(data.token);
      onLogin(data.username);
    } catch (err) {
      setError(err?.error || "Login failed. Check your credentials.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-logo">
          <span className="logo-icon">⚕</span>
          <div>
            <h1 className="logo-title">MIRA</h1>
            <p className="logo-sub">Admin Console</p>
          </div>
        </div>
        <h2 className="login-heading">Sign In</h2>
        <p className="login-desc">Access the administrative dashboard</p>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit} noValidate className="login-form">
          <div className="field">
            <label htmlFor="username">Username</label>
            <input id="username" type="text" value={form.username} autoComplete="username"
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" value={form.password} autoComplete="current-password"
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
          </div>
          <button type="submit" className="btn btn--primary login-btn" disabled={busy}>
            {busy ? <><span className="spinner" /> Signing in…</> : "Sign In"}
          </button>
        </form>
        <p className="login-hint">Default: admin / admin123</p>
      </div>
    </div>
  );
}
