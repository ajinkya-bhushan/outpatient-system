const TOKEN_KEY = 'docconnect_token';

export function getApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured === 'same-origin') {
    return '';
  }
  return configured || 'http://127.0.0.1:10200';
}

export function getToken() {
  if (typeof window === 'undefined') {
    return null;
  }
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function parseBody(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export async function login({ provider_id, password, role }) {
  const response = await fetch(`${getApiBase()}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider_id, password, role }),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    const error = new Error(body.detail || 'Invalid provider ID or password');
    error.status = response.status;
    throw error;
  }
  if (body.token) {
    setToken(body.token);
  }
  return body;
}

export async function me() {
  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${getApiBase()}/api/v1/auth/me`, { headers });
  const body = await parseBody(response);
  if (!response.ok) {
    const error = new Error(body.detail || 'Invalid or expired session');
    error.status = response.status;
    throw error;
  }
  return body;
}

export async function logout() {
  try {
    await fetch(`${getApiBase()}/api/v1/auth/logout`, { method: 'POST' });
  } finally {
    clearToken();
  }
}
