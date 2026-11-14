import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Bookmark, Briefcase, ChevronDown, FileText, LogOut, Menu, Monitor, Moon, Shield, Sun, User, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { ButtonLink, Container, cx } from "../ui";
import Logo from "./Logo";

const navClass = ({ isActive }) =>
  cx("rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "text-brand" : "text-muted hover:text-text");

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const order = ["system", "light", "dark"];
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  const next = order[(order.indexOf(theme) + 1) % order.length];
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text"
      aria-label={`Theme: ${theme}. Switch to ${next}`}
      title={`Theme: ${theme}`}
    >
      <Icon className="size-5" />
    </button>
  );
}

function Avatar({ user }) {
  if (user.profile_picture) {
    return <img src={user.profile_picture} alt="" className="size-8 rounded-full object-cover" />;
  }
  const initials = (user.name || user.email).split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return <span className="grid size-8 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand-strong">{initials}</span>;
}

function AccountMenu({ user, logout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const location = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const item = "flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-surface-2";
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-full p-0.5 pr-2 hover:bg-surface-2"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Avatar user={user} />
        <ChevronDown className="size-4 text-muted" aria-hidden />
        <span className="sr-only">Account menu</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-2 w-60 rounded-xl border border-border bg-surface p-1.5 shadow-lg">
          <div className="border-b border-border px-3 pt-1.5 pb-2.5">
            <p className="truncate text-sm font-medium">{user.name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
          </div>
          <div className="pt-1.5">
            {user.company && (
              <Link role="menuitem" to="/company" className={item}>
                <Briefcase className="size-4" /> {user.company.name}
              </Link>
            )}
            <Link role="menuitem" to="/profile" className={item}>
              <User className="size-4" /> My profile
            </Link>
            <Link role="menuitem" to="/applications" className={item}>
              <FileText className="size-4" /> My applications
            </Link>
            <Link role="menuitem" to="/saved" className={item}>
              <Bookmark className="size-4" /> Saved roles
            </Link>
            <Link role="menuitem" to="/account/security" className={item}>
              <Shield className="size-4" /> Account and security
            </Link>
            <button role="menuitem" type="button" onClick={logout} className={cx(item, "w-full text-left text-danger")}>
              <LogOut className="size-4" /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Header() {
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const links = (
    <>
      <NavLink to="/opportunities" className={navClass}>Find roles</NavLink>
      {user ? (
        <NavLink to="/applications" className={navClass}>My applications</NavLink>
      ) : (
        <NavLink to="/companies/join" className={navClass}>For employers</NavLink>
      )}
      {user?.company && <NavLink to="/company" className={navClass}>Company dashboard</NavLink>}
    </>
  );

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface/90 backdrop-blur">
      <Container className="flex h-16 items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <Logo />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">{links}</nav>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {!loading && !user && (
            <div className="hidden items-center gap-2 sm:flex">
              <ButtonLink to="/login" variant="ghost">Sign in</ButtonLink>
              <ButtonLink to="/register">Create account</ButtonLink>
            </div>
          )}
          {user && <AccountMenu user={user} logout={logout} />}
          <button
            type="button"
            className="rounded-lg p-2 text-muted hover:bg-surface-2 md:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
          >
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </Container>
      {mobileOpen && (
        <div className="border-t border-border md:hidden">
          <Container className="flex flex-col gap-1 py-3">
            <nav className="flex flex-col" aria-label="Main">{links}</nav>
            {!user && (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <ButtonLink to="/login" variant="secondary">Sign in</ButtonLink>
                <ButtonLink to="/register">Create account</ButtonLink>
              </div>
            )}
          </Container>
        </div>
      )}
    </header>
  );
}
