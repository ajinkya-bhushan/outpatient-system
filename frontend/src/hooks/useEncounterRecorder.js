import { useCallback, useEffect, useRef, useState } from 'react';

// Ordered by preference. Opus in WebM is the best-supported combination in
// Chrome and Firefox; Safari only produces MP4/AAC. Both container extensions
// are in the backend's SUPPORTED_EXTENSIONS list, and its upload validation
// keys off the *extension*, so the filename has to match whatever we picked.
const CANDIDATE_TYPES = [
  { mimeType: 'audio/webm;codecs=opus', extension: 'webm' },
  { mimeType: 'audio/webm', extension: 'webm' },
  { mimeType: 'audio/mp4;codecs=mp4a.40.2', extension: 'mp4' },
  { mimeType: 'audio/mp4', extension: 'mp4' },
  { mimeType: 'audio/ogg;codecs=opus', extension: 'ogg' },
];

function pickRecordingType() {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return null;
  }
  return CANDIDATE_TYPES.find(
    (candidate) => MediaRecorder.isTypeSupported(candidate.mimeType),
  ) ?? null;
}

function describeMicError(error) {
  switch (error?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Microphone access was blocked. Allow it in your browser settings, then start the encounter again.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was found. Connect one, or upload a recording instead.';
    case 'NotReadableError':
      return 'The microphone is in use by another application.';
    default:
      return error?.message || 'Could not start the microphone.';
  }
}

/**
 * Record encounter audio from the microphone into a single File.
 *
 * `stop()` resolves the complete recording, which the caller then submits to
 * `/diarize` in one request. Chunked mid-recording refresh is deliberately not
 * here yet: the backend endpoint is file-at-a-time.
 */
export function useEncounterRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);

  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);

  const releaseStream = useCallback(() => {
    // Without this the browser's recording indicator stays lit.
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  useEffect(() => releaseStream, [releaseStream]);

  const start = useCallback(async () => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      const message = 'This browser cannot record audio. Upload a recording instead.';
      setError(message);
      throw new Error(message);
    }

    const type = pickRecordingType();
    if (!type) {
      const message = 'This browser cannot record a supported audio format. Upload a recording instead.';
      setError(message);
      throw new Error(message);
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (cause) {
      const message = describeMicError(cause);
      setError(message);
      throw new Error(message);
    }

    const recorder = new MediaRecorder(stream, { mimeType: type.mimeType });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data?.size > 0) {
        chunksRef.current.push(event.data);
      }
    };

    streamRef.current = stream;
    recorderRef.current = { recorder, type };
    recorder.start();
    setIsRecording(true);
  }, []);

  const stop = useCallback(
    () => new Promise((resolve, reject) => {
      const active = recorderRef.current;
      if (!active || active.recorder.state === 'inactive') {
        setIsRecording(false);
        releaseStream();
        resolve(null);
        return;
      }

      const { recorder, type } = active;
      recorder.onstop = () => {
        releaseStream();
        setIsRecording(false);

        const blob = new Blob(chunksRef.current, { type: type.mimeType });
        chunksRef.current = [];
        if (blob.size === 0) {
          const message = 'The recording came back empty. Check the microphone and try again.';
          setError(message);
          reject(new Error(message));
          return;
        }

        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        resolve(new File([blob], `encounter-${stamp}.${type.extension}`, { type: type.mimeType }));
      };
      recorder.stop();
    }),
    [releaseStream],
  );

  const cancel = useCallback(() => {
    const active = recorderRef.current;
    if (active && active.recorder.state !== 'inactive') {
      active.recorder.onstop = null;
      active.recorder.stop();
    }
    chunksRef.current = [];
    releaseStream();
    setIsRecording(false);
  }, [releaseStream]);

  return {
    isRecording,
    error,
    start,
    stop,
    cancel,
    clearError: useCallback(() => setError(null), []),
    isSupported: pickRecordingType() !== null,
  };
}

export default useEncounterRecorder;
