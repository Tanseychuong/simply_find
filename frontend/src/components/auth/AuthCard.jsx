import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Card, Container, Input, cx } from "../ui";

/** The centred card every sign-in, sign-up and email-link page uses. */
export default function AuthCard({ title, subtitle, children, footer, wide = false }) {
  return (
    <Container className="flex justify-center py-8 sm:py-16">
      <div className={cx("w-full", wide ? "max-w-lg" : "max-w-md")}>
        <Card className="p-6 sm:p-8">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </Card>
        {footer && <div className="mt-6 text-center text-sm text-muted">{footer}</div>}
      </div>
    </Container>
  );
}

/** Password input with a show/hide toggle. */
export function PasswordInput({ id, invalid, autoComplete = "current-password", ...props }) {
  const [shown, setShown] = useState(false);
  const fallbackId = useId();
  return (
    <div className="relative">
      <Input id={id || fallbackId} type={shown ? "text" : "password"} autoComplete={autoComplete} invalid={invalid} className="pr-10" {...props} />
      <button
        type="button"
        onClick={() => setShown((v) => !v)}
        className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted hover:text-text"
        aria-label={shown ? "Hide password" : "Show password"}
        aria-pressed={shown}
      >
        {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

export function Divider({ children }) {
  return (
    <div className="my-6 flex items-center gap-3 text-xs text-muted">
      <span className="h-px flex-1 bg-border" />
      {children}
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
