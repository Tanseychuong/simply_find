import { api } from "./client";

export const companiesApi = {
  publicProfile: (slug, config) => api.get(`/companies/${encodeURIComponent(slug)}/`, config).then((r) => r.data),
};
