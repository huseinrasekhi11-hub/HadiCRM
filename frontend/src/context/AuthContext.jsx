import { createContext, useContext, useEffect, useState } from "react";
import { login as apiLogin, getMe, clearRequestCache } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem("hadiflow_access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((me) => setUser(me))
      .catch(() => {
        localStorage.removeItem("hadiflow_access_token");
        localStorage.removeItem("hadiflow_refresh_token");
      })
      .finally(() => setLoading(false));
  }, []);

  // Session terminated by the API layer (expired refresh, 401): drop the
  // user so RequireAuth redirects to /login instead of leaving the UI in
  // a dead-token state. The event was dispatched before but never heard.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      setLoading(false);
    };
    window.addEventListener("auth-unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth-unauthorized", onUnauthorized);
  }, []);

  async function login(mobile, password) {
    setError(null);
    const tokens = await apiLogin(mobile, password);
    localStorage.setItem("hadiflow_access_token", tokens.access_token);
    localStorage.setItem("hadiflow_refresh_token", tokens.refresh_token);
    const me = await getMe();
    setUser(me);
    return me;
  }

  function logout() {
    localStorage.removeItem("hadiflow_access_token");
    localStorage.removeItem("hadiflow_refresh_token");
    clearRequestCache();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, error, setError, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
