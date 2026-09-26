import { createContext, useCallback, useContext, useRef, useState } from "react";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import "./Toast.css";

const ToastContext = createContext(null);

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback((message, type = "info") => {
    const id = ++idRef.current;
    setToasts((prev) => {
      // Keep max 3 toasts on screen
      const newToasts = [{ id, message, type }, ...prev];
      return newToasts.slice(0, 3);
    });
    setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-viewport">
        {toasts.map((t, index) => {
          const Icon = ICONS[t.type] || Info;
          return (
            <div 
              key={t.id} 
              className={`premium-toast premium-toast--${t.type}`}
              style={{ 
                "--index": index,
                "--offset": `${index * 12}px`,
                "--scale": 1 - (index * 0.05)
              }}
            >
              <div className="premium-toast__icon">
                <Icon size={18} strokeWidth={2.5} />
              </div>
              <span className="premium-toast__message">{t.message}</span>
              <button className="premium-toast__close" onClick={() => dismiss(t.id)}>
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
