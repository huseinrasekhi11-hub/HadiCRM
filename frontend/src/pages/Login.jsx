import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Phone, Lock, ArrowLeft, Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import ThemeToggle from "../components/ThemeToggle";
import "./Login.css";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(mobile, password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err.response && err.response.status === 401) {
        setError("شماره موبایل یا رمز عبور اشتباه است.");
      } else if (err.request && !err.response) {
        setError("اتصال به سرور برقرار نشد. ارتباط اینترنت را بررسی کنید.");
      } else {
        setError("ورود انجام نشد. دوباره تلاش کنید.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-layout">
      <div className="login-theme-toggle">
        <ThemeToggle />
      </div>

      {/* Brand panel — hidden on phones, where the form is the whole screen */}
      <div className="login-brand-panel">
        <div className="login-brand-panel__bg" aria-hidden="true" />
        <div className="login-brand-panel__content">
          <div className="login-logo-wrapper">
            <img src="/logo.png" alt="HadiFlow" className="login-logo" />
          </div>
          <h2 className="login-tagline">سامانه یکپارچه مدیریت فروش و ارتباط با مشتریان</h2>
        </div>
      </div>

      {/* Form panel */}
      <div className="login-form-panel">
        <div className="login-form-container">
          <div className="login-header">
            <div className="login-header__mark">
              <img src="/logo.png" alt="HadiFlow" className="login-header__logo" />
              <span className="login-header__rule" aria-hidden="true" />
            </div>
            <h1 className="login-title">ورود به حساب</h1>
            <p className="login-subtitle">شماره موبایل و رمز عبور خود را وارد کنید.</p>
          </div>

          <form onSubmit={handleSubmit} className="premium-form" noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="mobile">شماره موبایل</label>
              <div className="input-wrapper">
                <Phone size={18} className="input-icon" />
                <input
                  id="mobile"
                  type="tel"
                  inputMode="numeric"
                  autoComplete="username"
                  placeholder="09..."
                  value={mobile}
                  onChange={(e) => setMobile(e.target.value)}
                  required
                  aria-invalid={error ? "true" : undefined}
                  className="premium-input premium-input--with-icon premium-input--ltr"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">رمز عبور</label>
              <div className="input-wrapper">
                <Lock size={18} className="input-icon" />
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  aria-invalid={error ? "true" : undefined}
                  className="premium-input premium-input--with-icon premium-input--ltr"
                />
              </div>
            </div>

            {error && (
              <div className="form-error-banner" role="alert">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary btn-primary--large w-full" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 size={18} className="spin" />
                  در حال ورود…
                </>
              ) : (
                <>
                  ورود به پنل
                  <ArrowLeft size={18} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
