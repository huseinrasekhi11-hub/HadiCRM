import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import "./RequireAuth.css"; // We'll add a small CSS file for the loader

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="boot-loader">
          <img src="/logo.png" alt="HadiFlow" className="boot-logo" />
          <div className="boot-spinner">
            <div className="boot-spinner__track" />
            <div className="boot-spinner__head" />
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
