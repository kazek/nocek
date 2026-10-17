// Talking to the server. Errors arrive as codes, which the page translates.

export class ApiError extends Error {
  constructor(code, detail) {
    super(detail || code);
    this.code = code;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(data?.error ?? "failed", data?.detail);
  }
  return data;
}

export const get = (path) => api(path);
export const post = (path, body = {}) => api(path, { method: "POST", body });
export const put = (path, body) => api(path, { method: "PUT", body });
export const del = (path) => api(path, { method: "DELETE" });
