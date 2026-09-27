import { createContext, useContext } from "react";

/**
 * The auth context lives here — separate from `context/AuthContext.jsx`,
 * which only exports the provider component.
 *
 * Why the split? A module that exports both React components and
 * non-components (a hook, in this case) loses Fast Refresh: every save
 * reloads the whole page instead of patching the component in place, and
 * the linter flags it (`react/only-export-components`). Keeping the
 * context object and its consumer hook in a plain `.js` module leaves the
 * component file component-only.
 */
export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}
