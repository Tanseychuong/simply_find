import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { opportunitiesApi } from "../../api/opportunities";
import { useAuth } from "../../context/AuthContext";
import { cx } from "../ui";

/** Bookmark toggle. Signed-out visitors are sent to sign in first. */
export default function SaveButton({ opportunity, onChange, className, withLabel = false }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [saved, setSaved] = useState(Boolean(opportunity.is_saved));
  const [busy, setBusy] = useState(false);

  async function toggle(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
      return;
    }
    const next = !saved;
    setSaved(next); // optimistic
    setBusy(true);
    try {
      await (next ? opportunitiesApi.save(opportunity.id) : opportunitiesApi.unsave(opportunity.id));
      onChange?.(next);
    } catch {
      setSaved(!next);
    } finally {
      setBusy(false);
    }
  }

  const Icon = saved ? BookmarkCheck : Bookmark;
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${opportunity.title} from saved` : `Save ${opportunity.title}`}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-lg p-2 text-sm font-medium transition-colors",
        saved ? "text-brand" : "text-muted hover:text-text",
        "hover:bg-surface-2",
        className,
      )}
    >
      <Icon className={cx("size-5", saved && "fill-brand/15")} />
      {withLabel && <span>{saved ? "Saved" : "Save"}</span>}
    </button>
  );
}
