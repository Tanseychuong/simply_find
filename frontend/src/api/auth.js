import { api } from "./client";

export const authApi = {
  me: () => api.get("/auth/me/").then((r) => r.data),
  updateMe: (data) => api.patch("/auth/me/", data).then((r) => r.data),
  register: (data) => api.post("/auth/register/", data).then((r) => r.data),
  login: (email, password) => api.post("/auth/login/", { email, password }).then((r) => r.data),
  mfaLogin: (mfa_token, code) => api.post("/auth/mfa/login/", { mfa_token, code }).then((r) => r.data),
  google: (credential) => api.post("/auth/google/", { credential }).then((r) => r.data),
  logout: () => api.post("/auth/logout/").then((r) => r.data),
  verifyEmail: (token) => api.post("/auth/verify-email/", { token }).then((r) => r.data),
  resendVerification: () => api.post("/auth/verify-email/resend/").then((r) => r.data),
  passwordReset: (email) => api.post("/auth/password-reset/", { email }).then((r) => r.data),
  passwordResetConfirm: (data) => api.post("/auth/password-reset/confirm/", data).then((r) => r.data),
  mfaSetup: (password) => api.post("/auth/mfa/setup/", { password }).then((r) => r.data),
  mfaEnable: (code) => api.post("/auth/mfa/enable/", { code }).then((r) => r.data),
  mfaDisable: (password, code) => api.post("/auth/mfa/disable/", { password, code }).then((r) => r.data),
  deleteAccount: (data) => api.post("/auth/me/delete/", data).then((r) => r.data),
};
