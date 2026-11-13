// A small client for the Project Manager API (see the API's /docs for every endpoint).

const SESSION_KEY = "project-manager.session";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function apiBaseUrl() {
  const configured = window.PM_CONFIG && window.PM_CONFIG.apiBaseUrl;
  return (configured || "http://localhost:8000").replace(/\/+$/, "");
}

// The signed-in user: { token, username, expiresAt }. Kept for this browser tab only.
export const session = {
  get() {
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(SESSION_KEY));
    } catch {
      return null;
    }
    if (!saved || Date.now() >= saved.expiresAt) {
      this.clear();
      return null;
    }
    return saved;
  },
  save(value) {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } catch {
      // Storage can be unavailable (e.g. private windows); the user then signs in again on reload.
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // nothing saved, nothing to clear
    }
  },
};

// The message to show for an error response: FastAPI sends {"detail": "..."} or, for invalid input,
// {"detail": [{"loc": [...], "msg": "..."}, ...]}.
async function errorMessage(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    return `The server answered ${response.status}.`;
  }
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((problem) => {
        const field = (problem.loc || []).filter((part) => part !== "body" && part !== "query").join(".");
        return field ? `${field}: ${problem.msg}` : problem.msg;
      })
      .join("; ");
  }
  return `The server answered ${response.status}.`;
}

async function request(method, path, { json, form, query, auth = true, blob = false } = {}) {
  const url = new URL(apiBaseUrl() + path);
  for (const [name, value] of Object.entries(query || {})) url.searchParams.set(name, value);

  const headers = {};
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    body = form; // the browser sets the multipart Content-Type with its boundary
  }
  if (auth) {
    const current = session.get();
    if (current) headers.Authorization = `Bearer ${current.token}`;
  }

  let response;
  try {
    response = await fetch(url, { method, headers, body });
  } catch {
    throw new ApiError(0, `Can't reach the API at ${apiBaseUrl()}. Is it running?`);
  }

  if (!response.ok) {
    if (response.status === 401 && auth) {
      // Missing, expired or revoked token: the user has to sign in again.
      session.clear();
      window.dispatchEvent(new Event("session-ended"));
    }
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) return null;
  return blob ? response.blob() : response.json();
}

// --- auth ---

export function register(username, password, repeatPassword) {
  return request("POST", "/auth", {
    auth: false,
    json: { username, password, repeat_password: repeatPassword },
  });
}

export async function logIn(username, password) {
  const token = await request("POST", "/login", { auth: false, json: { username, password } });
  session.save({
    token: token.access_token,
    username,
    expiresAt: Date.now() + token.expires_in * 1000,
  });
}

export function logOut() {
  session.clear();
}

// --- projects ---

export const listProjects = () => request("GET", "/projects");
export const getProject = (id) => request("GET", `/project/${id}/info`);
export const createProject = (name, description) =>
  request("POST", "/projects", { json: { name, description: description || null } });
export const updateProject = (id, name, description) =>
  request("PUT", `/project/${id}/info`, { json: { name, description: description || null } });
export const deleteProject = (id) => request("DELETE", `/project/${id}`);
export const inviteUser = (id, username) => request("POST", `/project/${id}/invite`, { query: { user: username } });
export const shareProject = (id, email) => request("GET", `/project/${id}/share`, { query: { with: email } });

// --- documents ---

export function uploadDocuments(projectId, files) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return request("POST", `/project/${projectId}/documents`, { form });
}

export const downloadDocument = (id) => request("GET", `/document/${id}`, { blob: true });
export const deleteDocument = (id) => request("DELETE", `/document/${id}`);
