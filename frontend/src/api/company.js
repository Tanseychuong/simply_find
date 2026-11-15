import { api, apiUrl } from "./client";
import { cleanParams } from "./opportunities";

export const TEAM_ROLES = {
  owner: { label: "Owner", help: "Everything, including the team and roles" },
  admin: { label: "Admin", help: "Company profile, jobs and applicants; can invite admins and recruiters" },
  recruiter: { label: "Recruiter", help: "Jobs and applicants" },
};

export const QUESTION_KINDS = {
  short_text: "Short answer",
  long_text: "Long answer",
  file: "File (CV, transcript...)",
  url: "Link",
  yes_no: "Yes / No",
  choice: "Multiple choice",
};

export const JOB_STATUS = {
  pending: { label: "In review", tone: "accent" },
  approved: { label: "Live", tone: "success" },
  rejected: { label: "Not approved", tone: "danger" },
};

export const COMPANY_SIZES = ["1-10", "11-50", "51-200", "200+"];

/** Statuses a hiring team can set (withdrawn is the applicant's). */
export const HIRING_STATUSES = ["submitted", "reviewing", "shortlisted", "rejected", "hired"];
export const BULK_STATUSES = ["reviewing", "shortlisted", "rejected", "hired"];

const data = (r) => r.data;

export const companyApi = {
  register: (body) => api.post("/companies/", body).then(data),
  me: (config) => api.get("/companies/me/", config).then(data),
  update: (body) => api.patch("/companies/me/", body).then(data),
  uploadLogo: (file) => {
    const form = new FormData();
    form.append("logo", file);
    return api.post("/companies/me/logo/", form).then(data);
  },

  jobs: (config) => api.get("/companies/me/jobs/", config).then(data),
  job: (id, config) => api.get(`/companies/me/jobs/${id}/`, config).then(data),
  createJob: (body) => api.post("/companies/me/jobs/", body).then(data),
  updateJob: (id, body) => api.patch(`/companies/me/jobs/${id}/`, body).then(data),
  closeJob: (id) => api.post(`/companies/me/jobs/${id}/close/`).then(data),

  applications: (jobId, params, config) =>
    api.get(`/companies/me/jobs/${jobId}/applications/`, { params: cleanParams(params), ...config }).then(data),
  bulkStatus: (jobId, ids, status) => api.post(`/companies/me/jobs/${jobId}/applications/bulk/`, { ids, status }).then(data),
  updateApplication: (id, body) => api.patch(`/companies/me/applications/${id}/`, body).then(data),
  exportUrl: (jobId, kind, params) => {
    const qs = new URLSearchParams(cleanParams(params)).toString();
    const path = kind === "csv" ? "export.csv" : "print/";
    return apiUrl(`/api/companies/me/jobs/${jobId}/applications/${path}${qs ? `?${qs}` : ""}`);
  },

  team: (config) => api.get("/companies/me/team/", config).then(data),
  invite: (email, role) => api.post("/companies/me/team/invitations/", { email, role }).then(data),
  revokeInvite: (id) => api.delete(`/companies/me/team/invitations/${id}/`),
  changeRole: (memberId, role) => api.patch(`/companies/me/team/members/${memberId}/`, { role }).then(data),
  removeMember: (memberId) => api.delete(`/companies/me/team/members/${memberId}/`),
  invitation: (token, config) => api.get(`/companies/invitations/${encodeURIComponent(token)}/`, config).then(data),
  acceptInvitation: (token) => api.post(`/companies/invitations/${encodeURIComponent(token)}/`).then(data),
};

export const drivesApi = {
  mine: (config) => api.get("/drives/mine/", config).then(data),
  get: (id, config) => api.get(`/drives/mine/${id}/`, config).then(data),
  create: (body) => api.post("/drives/mine/", body).then(data),
  update: (id, body) => api.patch(`/drives/mine/${id}/`, body).then(data),
  remove: (id) => api.delete(`/drives/mine/${id}/`),
  qrUrl: (id) => apiUrl(`/api/drives/mine/${id}/qr.png`),
  students: (id, config) => api.get(`/drives/mine/${id}/students/`, config).then(data),
  signUp: (id, body) => api.post(`/drives/mine/${id}/students/`, body).then(data),
  deskDocument: (id, regId, { file, kind, title }) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("title", title);
    return api.post(`/drives/mine/${id}/students/${regId}/documents/`, form).then(data);
  },
  resendClaim: (id, regId) => api.post(`/drives/mine/${id}/students/${regId}/resend/`).then(data),
  publicDrive: (code, config) => api.get(`/drives/${encodeURIComponent(code.toUpperCase())}/`, config).then(data),
};
