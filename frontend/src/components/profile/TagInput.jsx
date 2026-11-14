import { useId, useState } from "react";
import { X } from "lucide-react";
import { cx } from "../ui";

/** A list of short values (skills, languages): Enter or comma adds, × removes. */
export default function TagInput({ id, value, onChange, max = 20, placeholder, suggestions = [], invalid }) {
  const [text, setText] = useState("");
  const listId = useId();
  const has = (v) => value.some((x) => x.toLowerCase() === v.toLowerCase());

  function add(raw) {
    const v = raw.replace(/,/g, " ").replace(/\s+/g, " ").trim().slice(0, 40);
    if (v && !has(v) && value.length < max) onChange([...value, v]);
    setText("");
  }

  return (
    <div>
      <div
        className={cx(
          "flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border bg-surface px-2 py-1.5 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20",
          invalid ? "border-danger" : "border-border",
        )}
      >
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-2.5 py-0.5 text-sm text-brand-strong">
            {v}
            <button type="button" onClick={() => onChange(value.filter((x) => x !== v))} aria-label={`Remove ${v}`} className="rounded-full hover:text-danger">
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        {value.length < max && (
          <input
            id={id}
            list={suggestions.length ? listId : undefined}
            value={text}
            placeholder={value.length ? "" : placeholder}
            onChange={(e) => {
              const v = e.target.value;
              if (v.endsWith(",")) add(v);
              else setText(v);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add(text);
              } else if (e.key === "Backspace" && !text && value.length) {
                onChange(value.slice(0, -1));
              }
            }}
            onBlur={() => text && add(text)}
            className="min-w-32 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-muted"
          />
        )}
      </div>
      {suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.filter((s) => !has(s)).map((s) => <option key={s} value={s} />)}
        </datalist>
      )}
      <p className="mt-1 text-xs text-muted">Press Enter after each one. {value.length}/{max}</p>
    </div>
  );
}
