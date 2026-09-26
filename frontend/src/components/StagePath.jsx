import { STATUS_ORDER, statusLabel, statusColor } from "../leadStatus";
import "./StagePath.css";

// Tap-to-advance pipeline path. Replaces the status dropdown as the
// primary progression control. Closed statuses are handled by the caller
// (they open StatusChangeModal for loss-reason / sale capture).
export default function StagePath({ currentStatus, onSelect, disabled = false }) {
  const currentIndex = STATUS_ORDER.indexOf(currentStatus);
  return (
    <div className="stage-path" aria-label="مراحل قیف فروش">
      <div className="stage-path__track">
        {STATUS_ORDER.map((status, i) => {
          const isCurrent = status === currentStatus;
          const isPast = i < currentIndex;
          const color = statusColor(status);
          return (
            <button
              key={status}
              type="button"
              className={[
                "stage-path__step",
                isCurrent ? "stage-path__step--current" : "",
                isPast ? "stage-path__step--past" : "",
              ].join(" ")}
              style={{ "--stage-color": color }}
              onClick={() => {
                if (!disabled && !isCurrent) onSelect(status);
              }}
              disabled={disabled || isCurrent}
              title={statusLabel(status)}
            >
              <span className="stage-path__dot" />
              <span className="stage-path__label">{statusLabel(status)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
