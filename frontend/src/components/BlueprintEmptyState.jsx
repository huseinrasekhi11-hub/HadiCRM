import { Sparkles } from "lucide-react";
import EmptyState from "./EmptyState";
import "./BlueprintEmptyState.css"; // preserved for legacy layout contexts

/**
 * Kept for backward compatibility. Delegates to the unified EmptyState.
 */
export default function BlueprintEmptyState({ title, subtitle, action, icon: Icon = Sparkles }) {
  return <EmptyState icon={Icon} title={title} subtitle={subtitle} action={action} />;
}
