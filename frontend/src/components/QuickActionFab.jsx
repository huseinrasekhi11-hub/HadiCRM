import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import NewLeadModal from "./NewLeadModal";
import "./QuickActionFab.css";

// The only legitimate GLOBAL quick action in this backend: tasks and
// activities are lead-scoped, so the FAB creates a lead and jumps to it.
export default function QuickActionFab() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <>
      <button className="quick-fab" onClick={() => setOpen(true)} aria-label="ثبت لید جدید">
        <Plus size={24} strokeWidth={2.5} />
      </button>
      {open && (
        <NewLeadModal
          onClose={() => setOpen(false)}
          onCreated={(lead) => {
            setOpen(false);
            navigate(`/leads/${lead.id}`);
          }}
        />
      )}
    </>
  );
}
