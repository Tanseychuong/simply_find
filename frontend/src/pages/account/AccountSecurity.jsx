import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Camera, Copy, Download, KeyRound, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage, fieldErrors } from "../../api/client";
import { PasswordInput } from "../../components/auth/AuthCard";
import GoogleButton, { googleEnabled } from "../../components/auth/GoogleButton";
import { safeNext } from "../../components/guards";
import { Alert, Badge, Button, Card, Container, Field, Input } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useTitle } from "../../lib/hooks";

function Section({ icon: Icon, title, description, children, tone }) {
  return (
    <Card className={tone === "danger" ? "border-danger/40 p-6" : "p-6"}>
      <div className="mb-5 flex items-start gap-3">
        <Icon className={tone === "danger" ? "mt-0.5 size-5 text-danger" : "mt-0.5 size-5 text-brand"} aria-hidden />
        <div>
          <h2 className="font-semibold">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}

function Details() {
  const { user, reload } = useAuth();
  const [name, setName] = useState(user.name);
  const [state, setState] = useState({ busy: false, error: null, saved: false });
  const [resend, setResend] = useState(null);
  const fileRef = useRef(null);

  async function save(data) {
    setState({ busy: true, error: null, saved: false });
    try {
      await authApi.updateMe(data);
      await reload();
      setState({ busy: false, error: null, saved: true });
    } catch (err) {
      const f = fieldErrors(err);
      setState({ busy: false, error: f.name || f.profile_picture || errorMessage(err), saved: false });
    }
  }

  function uploadPicture(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("profile_picture", file);
    save(form);
  }

  return (
    <Section icon={KeyRound} title="Your details">
      <div className="space-y-5">
        <div className="flex items-center gap-4">
          {user.profile_picture ? (
            <img src={user.profile_picture} alt="" className="size-16 rounded-full object-cover" />
          ) : (
            <span className="grid size-16 place-items-center rounded-full bg-brand-soft text-xl font-semibold text-brand-strong">
              {user.name.charAt(0).toUpperCase()}
            </span>
          )}
          <div>
            <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()} disabled={state.busy}>
              <Camera className="size-4" /> {user.profile_picture ? "Change photo" : "Add a photo"}
            </Button>
            <p className="mt-1 text-xs text-muted">JPG or PNG. Location data is removed.</p>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png" className="hidden" onChange={uploadPicture} />
          </div>
        </div>
        <form
          className="flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            save({ name: name.trim() });
          }}
        >
          <div className="flex-1">
            <Field label="Full name" htmlFor="name">
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
          </div>
          <Button type="submit" variant="secondary" loading={state.busy} disabled={!name.trim() || name.trim() === user.name}>Save</Button>
        </form>
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        {state.saved && <p className="text-sm text-success">Saved.</p>}
        <div>
          <p className="text-sm font-medium">Email</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
            {user.email}
            {user.email_verified ? <Badge tone="success">Confirmed</Badge> : <Badge tone="accent">Not confirmed</Badge>}
            {!user.email_verified && (
              <button
                type="button"
                className="font-medium text-brand hover:underline"
                onClick={async () => {
                  try {
                    setResend((await authApi.resendVerification()).detail);
                  } catch (err) {
                    setResend(errorMessage(err));
                  }
                }}
              >
                Send the link again
              </button>
            )}
          </div>
          {resend && <p className="mt-1 text-xs text-muted">{resend}</p>}
        </div>
      </div>
    </Section>
  );
}

function RecoveryCodes({ codes, onDone }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");
  function download() {
    const url = URL.createObjectURL(new Blob([`SimplyFind recovery codes\nEach code works once.\n\n${text}\n`], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "simplyfind-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="space-y-4">
      <Alert tone="success">Two-step sign-in is on.</Alert>
      <p className="text-sm">
        Save these recovery codes somewhere safe. If you lose your phone, each one lets you sign in once.
        <strong> We won't show them again.</strong>
      </p>
      <ul className="grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-4 font-mono text-sm">
        {codes.map((c) => <li key={c}>{c}</li>)}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
            } catch {
              setCopied(false);
            }
          }}
        >
          <Copy className="size-4" /> {copied ? "Copied" : "Copy"}
        </Button>
        <Button variant="secondary" size="sm" onClick={download}>
          <Download className="size-4" /> Download
        </Button>
        <Button size="sm" onClick={onDone}>I've saved them</Button>
      </div>
    </div>
  );
}

/**
 * The API's qr_svg is segno's inline SVG, written to sit inside HTML: it has
 * no xmlns, which a standalone SVG image needs to render at all.
 */
function qrDataUri(svg) {
  const withNs = svg.includes("xmlns=") ? svg : svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(withNs)}`;
}

function TwoStep() {
  const { user, signedInAs } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const asked = params.has("setup");
  const [step, setStep] = useState("idle"); // idle | password | scan | codes | disable
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState(null);
  const [codes, setCodes] = useState([]);
  const [state, setState] = useState({ busy: false, error: null });

  async function act(fn) {
    setState({ busy: true, error: null });
    try {
      await fn();
      setState({ busy: false, error: null });
    } catch (err) {
      const f = fieldErrors(err);
      setState({ busy: false, error: f.password || f.code || errorMessage(err) });
    }
  }

  const start = () =>
    act(async () => {
      setSetup(await authApi.mfaSetup(password));
      setPassword("");
      setStep("scan");
    });
  const enable = () =>
    act(async () => {
      const data = await authApi.mfaEnable(code.trim());
      setCodes(data.recovery_codes);
      setCode("");
      setStep("codes");
      signedInAs(data.user); // the new session counts as two-step verified
    });
  const disable = () =>
    act(async () => {
      const data = await authApi.mfaDisable(password, code.trim());
      setPassword("");
      setCode("");
      setStep("idle");
      signedInAs(data.user);
    });

  const passwordField = user.has_password && (
    <Field label="Your password" htmlFor="mfa-password">
      <PasswordInput id="mfa-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
    </Field>
  );
  const codeField = (
    <Field label="6-digit code from your app" htmlFor="mfa-code">
      <Input
        id="mfa-code"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="123456"
        className="max-w-40 text-center tracking-widest"
      />
    </Field>
  );

  return (
    <Section
      icon={user.mfa_enabled ? ShieldCheck : ShieldOff}
      title="Two-step sign-in"
      description="After your password, you also enter a code from an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, Authy...)."
    >
      {asked && !user.mfa_enabled && step !== "codes" && (
        <Alert tone="warning" className="mb-4">Company and staff tools need two-step sign-in. Set it up to continue.</Alert>
      )}
      {state.error && <Alert tone="danger" className="mb-4">{state.error}</Alert>}

      {step === "codes" ? (
        <RecoveryCodes
          codes={codes}
          onDone={() => {
            setStep("idle");
            const next = params.get("next");
            if (next) navigate(safeNext(next), { replace: true });
          }}
        />
      ) : user.mfa_enabled ? (
        step === "disable" ? (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); disable(); }}>
            {passwordField}
            {codeField}
            <div className="flex gap-2">
              <Button type="submit" variant="danger" loading={state.busy} disabled={code.length !== 6 || (user.has_password && !password)}>Turn off</Button>
              <Button type="button" variant="ghost" onClick={() => setStep("idle")}>Cancel</Button>
            </div>
            {user.mfa_required && <p className="text-xs text-muted">Your company role needs it, so you'll be asked to set it up again.</p>}
          </form>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Badge tone="success">On</Badge>
            <Button variant="secondary" size="sm" onClick={() => setStep("disable")}>Turn off or move to a new phone</Button>
          </div>
        )
      ) : step === "password" ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); start(); }}>
          {passwordField}
          <div className="flex gap-2">
            <Button type="submit" loading={state.busy} disabled={user.has_password && !password}>Continue</Button>
            <Button type="button" variant="ghost" onClick={() => setStep("idle")}>Cancel</Button>
          </div>
        </form>
      ) : step === "scan" && setup ? (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); enable(); }}>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            <li>Open your authenticator app and add an account.</li>
            <li>Scan this QR code, or type the key below.</li>
            <li>Enter the 6-digit code it shows.</li>
          </ol>
          <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
            {/* The SVG is generated by our API (segno), shown as an image: never injected as HTML. */}
            <img
              src={qrDataUri(setup.qr_svg)}
              alt="QR code for your authenticator app"
              className="size-44 rounded-lg bg-white p-2"
            />
            <div className="min-w-0 text-sm">
              <p className="text-muted">Key</p>
              <p className="font-mono break-all select-all">{setup.secret}</p>
            </div>
          </div>
          {codeField}
          <Button type="submit" loading={state.busy} disabled={code.length !== 6}>Turn on</Button>
        </form>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Badge tone={user.mfa_required ? "accent" : "neutral"}>{user.mfa_required ? "Required for your role" : "Off"}</Badge>
          <Button size="sm" onClick={() => (user.has_password ? setStep("password") : start())} loading={state.busy}>Set it up</Button>
        </div>
      )}
    </Section>
  );
}

function DeleteAccount() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [state, setState] = useState({ busy: false, error: null, done: null });

  async function remove(e, confirmation = { password }) {
    e?.preventDefault();
    setState({ busy: true, error: null, done: null });
    try {
      const data = await authApi.deleteAccount(confirmation);
      setState({ busy: false, error: null, done: data.detail });
      setTimeout(logout, 4000); // long enough to read the message
    } catch (err) {
      setState({ busy: false, error: fieldErrors(err).password || errorMessage(err), done: null });
    }
  }

  return (
    <Section
      icon={Trash2}
      tone="danger"
      title="Delete your account"
      description="Your account is deactivated straight away and deleted for good after 14 days, with your profile, documents and applications. We'll email you how to undo it in that time."
    >
      {state.done ? (
        <Alert tone="success">{state.done} Signing you out...</Alert>
      ) : !open ? (
        <Button variant="secondary" onClick={() => setOpen(true)}>Delete my account</Button>
      ) : !user.has_password ? (
        <div className="space-y-3">
          {state.error && <Alert tone="danger">{state.error}</Alert>}
          <p className="text-sm">Your account was created with Google. Confirm with the same Google account to delete it.</p>
          {googleEnabled ? (
            <GoogleButton text="continue_with" onCredential={(credential) => remove(null, { google_credential: credential })} />
          ) : (
            <Alert tone="warning">Google sign-in isn't set up on this site, so this can't be confirmed here. Contact us to delete your account.</Alert>
          )}
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={remove}>
          {state.error && <Alert tone="danger">{state.error}</Alert>}
          <Field label="Enter your password to confirm" htmlFor="delete-password">
            <PasswordInput id="delete-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" loading={state.busy} disabled={!password}>Delete my account</Button>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </form>
      )}
    </Section>
  );
}

export default function AccountSecurity() {
  useTitle("Account and security");
  return (
    <Container className="py-6 sm:py-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-6 text-3xl font-bold tracking-tight">Account and security</h1>
        <div className="space-y-6">
          <Details />
          <TwoStep />
          <DeleteAccount />
        </div>
      </div>
    </Container>
  );
}
