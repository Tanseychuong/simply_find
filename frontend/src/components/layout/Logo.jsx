import { Link } from "react-router-dom";

export default function Logo({ className = "" }) {
  return (
    <Link to="/" className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`} aria-label="SimplyFind home">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-brand" />
        <circle cx="14" cy="14" r="6.5" fill="none" strokeWidth="3" className="stroke-on-brand" />
        <path d="M19 19l5.5 5.5" strokeWidth="3.2" strokeLinecap="round" className="stroke-accent" />
      </svg>
      <span className="text-lg">
        Simply<span className="text-brand">Find</span>
      </span>
    </Link>
  );
}
