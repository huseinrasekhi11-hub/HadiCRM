import { createContext, useContext } from "react";

/** See the note in `useAuth.js` for why the context is not in the .jsx file. */
export const ToastContext = createContext(null);

export function useToast() {
  return useContext(ToastContext);
}
