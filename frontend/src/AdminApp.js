import React, { useState, useEffect } from "react";
import AdminLogin from "./AdminLogin";
import AdminDashboard from "./AdminDashboard";
import { isLoggedIn, clearToken } from "./api";

export default function AdminApp() {
  const [loggedIn,  setLoggedIn]  = useState(isLoggedIn());
  const [username,  setUsername]  = useState(localStorage.getItem("mira_username") || "admin");

  const handleLogin = (uname) => {
    setUsername(uname);
    localStorage.setItem("mira_username", uname);
    setLoggedIn(true);
  };

  const handleLogout = () => {
    clearToken();
    localStorage.removeItem("mira_username");
    setLoggedIn(false);
  };

  if (!loggedIn) return <AdminLogin onLogin={handleLogin} />;
  return <AdminDashboard username={username} onLogout={handleLogout} />;
}
