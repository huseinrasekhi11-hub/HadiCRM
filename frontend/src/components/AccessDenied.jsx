import { ShieldOff } from "lucide-react";
import "./Scaffold.css";

export default function AccessDenied() {
  return (
    <div className="scaffold">
      <div className="scaffold__icon scaffold__icon--danger"><ShieldOff size={28} strokeWidth={1.8} /></div>
      <h2 className="scaffold__title">دسترسی مجاز نیست</h2>
      <p className="scaffold__subtitle">این بخش فقط برای مدیر سیستم و مدیرعامل در دسترس است.</p>
    </div>
  );
}
