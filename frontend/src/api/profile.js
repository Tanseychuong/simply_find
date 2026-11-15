import { api, apiUrl } from "./client";

export const DOCUMENT_KINDS = {
  transcript: "Transcript",
  certificate: "Certificate or diploma",
  cv: "CV",
  recommendation: "Recommendation letter",
  id_document: "ID document",
  other: "Other",
};

export const CREDENTIAL_PROVIDERS = {
  coursera: "Coursera",
  edx: "edX",
  credly: "Credly",
  linkedin_learning: "LinkedIn Learning",
  open_badge: "Open Badge",
  other: "Other",
};

/** check_status -> how the website shows it. */
export const CHECK_STATUS = {
  verified: { label: "Verified with the issuer", tone: "success" },
  recognised_link: { label: "Link on the provider's site", tone: "brand" },
  unchecked: { label: "Not checked", tone: "neutral" },
  failed: { label: "Couldn't be verified", tone: "danger" },
};

export const APPLICATION_STATUS = {
  submitted: { label: "Submitted", tone: "neutral" },
  reviewing: { label: "In review", tone: "brand" },
  shortlisted: { label: "Shortlisted", tone: "success" },
  hired: { label: "Hired", tone: "success" },
  rejected: { label: "Not selected", tone: "danger" },
  withdrawn: { label: "Withdrawn", tone: "neutral" },
};

export const ACCEPTED_FILES = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
export const MAX_UPLOAD_MB = 5; // backend MAX_UPLOAD_MB

export const profileApi = {
  get: (config) => api.get("/profile/", config).then((r) => r.data),
  update: (data) => api.patch("/profile/", data).then((r) => r.data),

  documents: (config) => api.get("/profile/documents/", config).then((r) => r.data),
  uploadDocument: ({ file, kind, title }, onUploadProgress) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("title", title);
    return api.post("/profile/documents/", form, { onUploadProgress }).then((r) => r.data);
  },
  renameDocument: (id, title) => api.patch(`/profile/documents/${id}/`, { title }).then((r) => r.data),
  deleteDocument: (id) => api.delete(`/profile/documents/${id}/`),
  documentFileUrl: (id) => apiUrl(`/api/profile/documents/${id}/file/`),

  credentials: (config) => api.get("/profile/credentials/", config).then((r) => r.data),
  addCredential: (data) => api.post("/profile/credentials/", data).then((r) => r.data),
  deleteCredential: (id) => api.delete(`/profile/credentials/${id}/`),
  recheckCredential: (id) => api.post(`/profile/credentials/${id}/check/`).then((r) => r.data),

  accessLog: (config) => api.get("/profile/access-log/", config).then((r) => r.data),
  eligibility: (opportunityId, config) => api.get(`/profile/eligibility/${opportunityId}/`, config).then((r) => r.data),
};

export const applicationsApi = {
  mine: (config) => api.get("/applications/", config).then((r) => r.data),
  /** `answers`: {requirementId: string | File | "vault:<id>"} */
  submit: (opportunityId, answers, onUploadProgress) => {
    const form = new FormData();
    form.append("opportunity", String(opportunityId));
    form.append("consent", "true");
    for (const [id, value] of Object.entries(answers)) {
      if (value === undefined || value === null || value === "") continue;
      form.append(`answer_${id}`, value);
    }
    return api.post("/applications/", form, { onUploadProgress }).then((r) => r.data);
  },
  withdraw: (id) => api.post(`/applications/${id}/withdraw/`).then((r) => r.data),
  answerFileUrl: (answerId) => apiUrl(`/api/applications/answers/${answerId}/file/`),
};
