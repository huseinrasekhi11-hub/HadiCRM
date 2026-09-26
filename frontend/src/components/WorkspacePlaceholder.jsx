import { Construction } from "lucide-react";
import "./Scaffold.css";

export default function WorkspacePlaceholder({ title, subtitle, part }) {
  return (
    <div className="scaffold">
      <div className="scaffold__icon"><Construction size={28} strokeWidth={1.8} /></div>
      <h2 className="scaffold__title">{title}</h2>
      <p className="scaffold__subtitle">{subtitle}</p>
      <p className="scaffold__part">این کارگاه در بخش {part} به‌طور کامل ساخته می‌شود.</p>
    </div>
  );
}
