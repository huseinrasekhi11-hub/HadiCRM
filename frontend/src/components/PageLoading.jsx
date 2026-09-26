import { Loader2 } from "lucide-react";

export default function PageLoading({ label = "در حال بارگذاری…" }) {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <Loader2 size={22} className="spin" />
      <span>{label}</span>
    </div>
  );
}
