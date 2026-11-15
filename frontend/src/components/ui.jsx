/* Small building blocks shared by every page. */
import { forwardRef } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";

export function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

export function Container({ className, children }) {
  return <div className={cx("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
}

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60";
const BUTTON_VARIANTS = {
  primary: "bg-brand text-on-brand hover:bg-brand-strong",
  secondary: "border border-border bg-surface text-text hover:bg-surface-2",
  ghost: "text-text hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90",
};
const BUTTON_SIZES = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base" };

export function buttonClass({ variant = "primary", size = "md", className } = {}) {
  return cx(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size], className);
}

export function Button({ variant, size, className, loading, disabled, children, ...props }) {
  return (
    <button className={buttonClass({ variant, size, className })} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function ButtonLink({ variant, size, className, ...props }) {
  return <Link className={buttonClass({ variant, size, className })} {...props} />;
}

export function Spinner({ className, label = "Loading" }) {
  return (
    <div className={cx("flex items-center justify-center py-16 text-muted", className)} role="status">
      <Loader2 className="size-6 animate-spin" aria-hidden />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function Card({ className, children, ...props }) {
  return (
    <div className={cx("rounded-xl border border-border bg-surface", className)} {...props}>
      {children}
    </div>
  );
}

export function Alert({ tone = "info", className, children }) {
  const tones = {
    info: "border-brand/30 bg-brand-soft text-text",
    warning: "border-accent/40 bg-accent-soft text-text",
    danger: "border-danger/30 bg-danger-soft text-danger",
    success: "border-success/30 bg-success-soft text-success",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("rounded-lg border px-4 py-3 text-sm", tones[tone], className)}>
      {children}
    </div>
  );
}

export function Field({ label, error, hint, htmlFor, children }) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={htmlFor} className="block text-sm font-medium">
          {label}
        </label>
      )}
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

const INPUT =
  "block w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20";

export const Input = forwardRef(function Input({ className, invalid, ...props }, ref) {
  return <input ref={ref} className={cx(INPUT, "h-10", invalid && "border-danger", className)} aria-invalid={invalid || undefined} {...props} />;
});

export const Select = forwardRef(function Select({ className, invalid, children, ...props }, ref) {
  return (
    <select ref={ref} className={cx(INPUT, "h-10", invalid && "border-danger", className)} aria-invalid={invalid || undefined} {...props}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef(function Textarea({ className, invalid, ...props }, ref) {
  return <textarea ref={ref} className={cx(INPUT, "min-h-24", invalid && "border-danger", className)} aria-invalid={invalid || undefined} {...props} />;
});

export function Badge({ tone = "neutral", className, children }) {
  const tones = {
    neutral: "bg-surface-2 text-muted",
    brand: "bg-brand-soft text-brand-strong",
    accent: "bg-accent-soft text-text",
    success: "bg-success-soft text-success",
    danger: "bg-danger-soft text-danger",
  };
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center px-4 py-16 text-center">
      {Icon && <Icon className="mb-4 size-10 text-muted" aria-hidden />}
      <h2 className="text-lg font-semibold">{title}</h2>
      {children && <p className="mt-2 max-w-md text-sm text-muted">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
