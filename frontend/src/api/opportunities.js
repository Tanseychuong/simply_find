import { api } from "./client";

/** Drops empty filters so URLs stay clean (?role_type=internship, not ?search=&paid=). */
export function cleanParams(params = {}) {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  );
}

export const opportunitiesApi = {
  list: (params, config) => api.get("/opportunities/", { params: cleanParams(params), ...config }).then((r) => r.data),
  get: (id, config) => api.get(`/opportunities/${id}/`, config).then((r) => r.data),
  categories: (config) => api.get("/opportunities/categories/", config).then((r) => r.data),
  locations: (config) => api.get("/opportunities/locations/", config).then((r) => r.data),
  stats: (config) => api.get("/opportunities/stats/", config).then((r) => r.data),
  save: (id) => api.post(`/opportunities/${id}/save/`),
  unsave: (id) => api.delete(`/opportunities/${id}/unsave/`),
  saved: (params) => api.get("/opportunities/saved/", { params: cleanParams(params) }).then((r) => r.data),
};
