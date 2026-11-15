import { useId, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { ACCEPTED_FILES, DOCUMENT_KINDS, MAX_UPLOAD_MB, profileApi } from "../../api/profile";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Button, Field, Input, Select, cx } from "../ui";

export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Checks the browser can do before sending: type and size. The server checks the real type again. */
export function checkFile(file) {
  if (!file) return "Choose a file.";
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) return "Upload a PDF, JPG or PNG.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `Files can be up to ${MAX_UPLOAD_MB} MB. This one is ${formatSize(file.size)}.`;
  return null;
}

const titleFromName = (name) => name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().slice(0, 120);

/** Upload one document to the vault. `onUploaded(document)` after it's stored and scanned. */
export default function DocumentUpload({ onUploaded, defaultKind = "transcript", onCancel }) {
  const id = useId();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [kind, setKind] = useState(defaultKind);
  const [title, setTitle] = useState("");
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState({ busy: false, progress: 0, error: null });

  function pick(f) {
    const problem = checkFile(f);
    setState({ busy: false, progress: 0, error: problem });
    if (problem) return;
    setFile(f);
    if (!title) setTitle(titleFromName(f.name));
  }

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, progress: 0, error: null });
    try {
      const doc = await profileApi.uploadDocument({ file, kind, title: title.trim() || titleFromName(file.name) }, (ev) =>
        setState((s) => ({ ...s, progress: ev.total ? Math.round((100 * ev.loaded) / ev.total) : 0 })),
      );
      setFile(null);
      setTitle("");
      setState({ busy: false, progress: 0, error: null });
      onUploaded(doc);
    } catch (err) {
      const f = fieldErrors(err);
      setState({ busy: false, progress: 0, error: f.file || f.kind || f.title || errorMessage(err) });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface-2/50 p-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        className={cx(
          "flex flex-col items-center rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors",
          drag ? "border-brand bg-brand-soft" : "border-border bg-surface",
        )}
      >
        <UploadCloud className="mb-2 size-8 text-muted" aria-hidden />
        {file ? (
          <p className="text-sm font-medium break-all">
            {file.name} <span className="font-normal text-muted">({formatSize(file.size)})</span>
          </p>
        ) : (
          <p className="text-sm text-muted">Drag a file here, or</p>
        )}
        <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => inputRef.current?.click()}>
          {file ? "Choose another file" : "Choose a file"}
        </Button>
        <p className="mt-2 text-xs text-muted">PDF, JPG or PNG, up to {MAX_UPLOAD_MB} MB. Every file is scanned for viruses.</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_FILES}
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="What is it?" htmlFor={`${id}-kind`}>
          <Select id={`${id}-kind`} value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(DOCUMENT_KINDS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Name" htmlFor={`${id}-title`}>
          <Input id={`${id}-title`} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. BSc transcript, year 3" />
        </Field>
      </div>
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      {state.busy && (
        <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-brand transition-all" style={{ width: `${state.progress}%` }} />
        </div>
      )}
      <div className="flex gap-2">
        <Button type="submit" loading={state.busy} disabled={!file}>{state.busy && state.progress === 100 ? "Scanning..." : "Upload"}</Button>
        {onCancel && <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
