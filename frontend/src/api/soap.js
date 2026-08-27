import { getApiBase, getToken } from './auth';

const POLL_MS = 2000;

async function parseBody(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function asError(body, fallback) {
  const detail = body.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  return body.message || fallback;
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      method,
      headers: {
        ...authHeaders(),
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (cause) {
    if (cause.name === 'AbortError') {
      throw cause;
    }
    const error = new Error('Could not reach the SOAP service.');
    error.cause = cause;
    throw error;
  }

  const payload = await parseBody(response);
  if (!response.ok) {
    const error = new Error(asError(payload, 'SOAP request failed.'));
    error.status = response.status;
    throw error;
  }
  return payload;
}

/** Start transcript → Comprehend → Aava. Returns 202 job payload. */
export async function createSoap({ transcript, encounterId, jobId, language, signal } = {}) {
  return request('/api/v1/soap/create', {
    method: 'POST',
    signal,
    body: {
      transcript,
      encounter_id: encounterId || undefined,
      job_id: jobId || undefined,
      language: language || undefined,
    },
  });
}

export async function getSoapJob(soapJobId, { signal } = {}) {
  return request(`/api/v1/soap/jobs/${encodeURIComponent(soapJobId)}`, { signal });
}

export async function getSoapNote(soapNoteId, { signal } = {}) {
  return request(`/api/v1/soap/notes/${encodeURIComponent(soapNoteId)}`, { signal });
}

export async function getSoapNoteForEncounter(encounterId, { signal } = {}) {
  return request(`/api/v1/soap/encounters/${encodeURIComponent(encounterId)}`, { signal });
}

export function sectionText(soapNote, sectionType) {
  const section = soapNote?.sections?.find((item) => item.section_type === sectionType);
  return section?.ai_generated_text || '';
}

export { POLL_MS };
