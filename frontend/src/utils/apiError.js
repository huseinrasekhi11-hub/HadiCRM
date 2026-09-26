/**
 * Turn any axios/FastAPI error into a string safe to render in JSX.
 *
 * FastAPI returns `detail` as a plain string for HTTPException, but as an
 * ARRAY OF OBJECTS for validation errors (HTTP 422). Several modals used to
 * do `setError(err.response.data.detail)` and render it directly, which
 * throws "Objects are not valid as a React child" and unmounts the whole
 * modal on the first validation error.
 */
export function getErrorMessage(err, fallback = "خطایی رخ داد. دوباره تلاش کنید.") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d === "string") return d;
        const field = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        const msg = typeof d?.msg === "string" ? d.msg.replace(/^Value error, /, "") : "";
        return msg ? (field ? `${field}: ${msg}` : msg) : "";
      })
      .filter(Boolean);
    if (msgs.length) return msgs.join(" — ");
  }
  if (detail && typeof detail === "object" && typeof detail.msg === "string") return detail.msg;
  if (!err?.response) return "ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.";
  return fallback;
}
