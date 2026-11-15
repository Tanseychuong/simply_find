import { Link } from "react-router-dom";
import { Container } from "../ui";
import Logo from "./Logo";

export default function Footer() {
  return (
    <footer className="mt-12 border-t sm:mt-16 border-border bg-surface">
      <Container className="grid grid-cols-2 gap-x-6 gap-y-8 py-8 sm:grid-cols-[2fr_1fr_1fr] sm:py-10">
        <div className="col-span-2 space-y-3 sm:col-span-1">
          <Logo />
          <p className="max-w-sm text-sm text-muted">
            Internships, graduate programmes and entry-level roles for students and recent graduates. Keep your
            transcripts and certificates in one place and apply with them.
          </p>
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Students</h2>
          <ul className="space-y-2 text-sm text-muted">
            <li><Link className="hover:text-text" to="/opportunities">Find roles</Link></li>
            <li><Link className="hover:text-text" to="/register">Create an account</Link></li>
            <li><Link className="hover:text-text" to="/profile">Your profile and documents</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Employers</h2>
          <ul className="space-y-2 text-sm text-muted">
            <li><Link className="hover:text-text" to="/companies/join">Hire on SimplyFind</Link></li>
            <li><Link className="hover:text-text" to="/company">Company dashboard</Link></li>
            <li><Link className="hover:text-text" to="/privacy">Privacy</Link></li>
          </ul>
        </div>
      </Container>
      <Container className="border-t border-border py-5 text-xs text-muted">© {new Date().getFullYear()} SimplyFind</Container>
    </footer>
  );
}
