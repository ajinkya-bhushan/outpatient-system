import { getApiBase, getToken } from './auth';

// Mirrors the backend's MAX_AUDIO_SIZE_MB / MAX_AUDIO_DURATION_SECONDS defaults.
// Checked here only so an oversized file fails instantly instead of after a
// multi-minute upload; the backend remains the authority.
export const MAX_AUDIO_SIZE_MB = 50;
export const MAX_AUDIO_DURATION_SECONDS = 3600;

export const SUPPORTED_EXTENSIONS = [
  '.wav', '.mp3', '.flac', '.ogg', '.oga', '.opus', '.m4a',
  '.mp4', '.aac', '.webm', '.mkv', '.wma', '.aiff', '.amr',
];

async function parseBody(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function extensionOf(filename) {
  const dot = filename.lastIndexOf('.');
  return dot === -1 ? '' : filename.slice(dot).toLowerCase();
}

/**
 * Read a media file's duration without decoding it.
 *
 * Resolves `null` when the browser cannot read the metadata — some containers
 * (notably a `MediaRecorder` WebM, which has no duration in its header) simply
 * do not carry it. A missing duration is not a rejection; ffprobe will
 * establish the real one server-side.
 */
export function probeDuration(file) {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || typeof window.Audio !== 'function') {
      resolve(null);
      return;
    }
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    const done = (value) => {
      URL.revokeObjectURL(url);
      audio.removeAttribute('src');
      resolve(value);
    };
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      const { duration } = audio;
      done(Number.isFinite(duration) && duration > 0 ? duration : null);
    };
    audio.onerror = () => done(null);
    audio.src = url;
  });
}

/** Throw a user-facing Error if the file cannot possibly be accepted. */
export async function validateAudioFile(file) {
  if (!file || file.size === 0) {
    throw new Error('That file is empty. Pick an audio recording and try again.');
  }

  const sizeMb = file.size / (1024 * 1024);
  if (sizeMb > MAX_AUDIO_SIZE_MB) {
    throw new Error(
      `That file is ${sizeMb.toFixed(1)} MB, over the ${MAX_AUDIO_SIZE_MB} MB limit.`,
    );
  }

  const extension = extensionOf(file.name);
  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    throw new Error(
      `${extension || 'That file type'} is not a supported audio format. `
      + `Try ${SUPPORTED_EXTENSIONS.slice(0, 5).join(', ')} or similar.`,
    );
  }

  const duration = await probeDuration(file);
  if (duration !== null && duration > MAX_AUDIO_DURATION_SECONDS) {
    const minutes = Math.round(duration / 60);
    throw new Error(
      `That recording is ${minutes} minutes long, over the `
      + `${MAX_AUDIO_DURATION_SECONDS / 60} minute limit.`,
    );
  }

  return { duration };
}

/**
 * Transcribe and diarize one audio file.
 *
 * `/diarize` is synchronous and a long encounter takes tens of seconds, so
 * callers should pass an `AbortController` signal to stay cancellable.
 */
export async function diarizeAudio(file, { numSpeakers, encounterId, language, signal } = {}) {
  await validateAudioFile(file);

  const form = new FormData();
  form.append('file', file, file.name);
  if (numSpeakers !== undefined && numSpeakers !== null) {
    form.append('num_speakers', String(numSpeakers));
  }
  if (encounterId) {
    form.append('encounter_id', encounterId);
  }
  if (language) {
    form.append('language', language);
  }

  const token = getToken();
  let response;
  try {
    response = await fetch(`${getApiBase()}/api/v1/stt/diarize`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal,
    });
  } catch (cause) {
    if (cause.name === 'AbortError') {
      throw cause;
    }
    const error = new Error('Could not reach the transcription service.');
    error.cause = cause;
    throw error;
  }

  const body = await parseBody(response);
  if (!response.ok) {
    const error = new Error(body.detail || body.message || 'Transcription failed.');
    error.status = response.status;
    throw error;
  }
  return body;
}

/** URL of the 16 kHz WAV a job was transcribed from. Supports Range requests. */
export function jobAudioUrl(jobId) {
  return `${getApiBase()}/api/v1/stt/jobs/${jobId}/audio`;
}

export async function getEngineStatus() {
  const response = await fetch(`${getApiBase()}/api/v1/stt/engine`);
  const body = await parseBody(response);
  if (!response.ok) {
    const error = new Error(body.detail || 'Could not read STT engine status.');
    error.status = response.status;
    throw error;
  }
  return body;
}
