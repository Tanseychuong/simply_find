/**
 * An external link from listing data (ingested or submitted), only if it is
 * http(s). Anything else (javascript:, data:) becomes null and isn't rendered.
 */
export function safeExternalUrl(value) {
  if (!value || typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function hostOf(value) {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
