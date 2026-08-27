import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AppSidebar from '../components/AppSidebar.jsx';
import ExtractionTag from '../components/ExtractionTag.jsx';
import Icon from '../components/Icon.jsx';
import TopBar from '../components/TopBar.jsx';
import TranscriptBubble from '../components/TranscriptBubble.jsx';
import { createSoap } from '../api/soap.js';
import { diarizeAudio, jobAudioUrl } from '../api/stt.js';
import useEncounterRecorder from '../hooks/useEncounterRecorder.js';

const CLINICIAN_LABEL = 'Dr. Smith';
const PATIENT_LABEL = 'Marcus';

export function formatClock(totalSeconds) {
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const seconds = String(Math.floor(totalSeconds % 60)).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

/**
 * Decide which anonymous cluster is the clinician.
 *
 * Diarization cannot know: `speaker_0` is simply the first cluster the
 * algorithm formed, and on the two-party fixture the transcript actually opens
 * with `speaker_1`. So this assigns by *first appearance* rather than by id and
 * lets the caller flip the assignment.
 */
export function resolveSpeakerRoles(turns, clinicianFirst = true) {
  const order = [...new Set(turns.map((turn) => turn.speaker_id))];
  return new Map(order.map((speakerId, index) => {
    const isFirstToSpeak = index === 0;
    return [speakerId, isFirstToSpeak === clinicianFirst ? 'clinician' : 'patient'];
  }));
}

export function formatLabelledTranscript(turns, clinicianFirst = true) {
  const roles = resolveSpeakerRoles(turns, clinicianFirst);
  return turns.map((turn) => {
    const role = roles.get(turn.speaker_id) === 'clinician' ? 'Doctor' : 'Patient';
    return `${role}: ${turn.text}`;
  }).join('\n');
}

function RecordingScreen({ go, setSession, sidebarCollapsed, onToggleSidebar }) {
  // idle -> recording -> processing -> ready, plus error as a terminal branch.
  const [status, setStatus] = useState('idle');
  const [turns, setTurns] = useState([]);
  const [jobId, setJobId] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [playingIndex, setPlayingIndex] = useState(null);
  const [clinicianFirst, setClinicianFirst] = useState(true);

  const [startingNote, setStartingNote] = useState(false);

  const recorder = useEncounterRecorder();
  const fileInputRef = useRef(null);
  const audioRef = useRef(null);
  const requestRef = useRef(null);

  const isBusy = status === 'recording' || status === 'processing' || startingNote;

  useEffect(() => {
    if (status !== 'recording') {
      return undefined;
    }
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => () => requestRef.current?.abort(), []);

  const roles = useMemo(() => resolveSpeakerRoles(turns, clinicianFirst), [turns, clinicianFirst]);

  const stopPlayback = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
    }
    setPlayingIndex(null);
  }, []);

  const submitAudio = useCallback(async (file) => {
    stopPlayback();
    setError(null);
    setTurns([]);
    setJobId(null);
    setStatus('processing');

    const controller = new AbortController();
    requestRef.current = controller;

    try {
      const result = await diarizeAudio(file, { signal: controller.signal });
      setTurns(result.turns ?? []);
      setJobId(result.job_id ?? null);
      setStatus('ready');
    } catch (cause) {
      if (cause.name === 'AbortError') {
        setStatus('idle');
        return;
      }
      setError(cause.message);
      setStatus('error');
    } finally {
      requestRef.current = null;
    }
  }, [stopPlayback]);

  const startEncounter = async () => {
    setError(null);
    setElapsed(0);
    try {
      await recorder.start();
      setStatus('recording');
    } catch (cause) {
      setError(cause.message);
      setStatus('error');
    }
  };

  const endEncounter = async () => {
    try {
      const file = await recorder.stop();
      if (file) {
        await submitAudio(file);
      } else {
        setStatus('idle');
      }
    } catch (cause) {
      setError(cause.message);
      setStatus('error');
    }
  };

  const handleFilePicked = async (event) => {
    const file = event.target.files?.[0];
    // Reset so picking the same file twice still fires a change event.
    event.target.value = '';
    if (file) {
      setElapsed(0);
      await submitAudio(file);
    }
  };

  const cancelProcessing = () => {
    requestRef.current?.abort();
  };

  /** Replay a single turn by seeking the one shared audio element. */
  const playTurn = (index) => {
    const audio = audioRef.current;
    const turn = turns[index];
    if (!audio || !turn) {
      return;
    }
    if (playingIndex === index) {
      stopPlayback();
      return;
    }
    audio.currentTime = turn.start;
    setPlayingIndex(index);
    audio.play().catch(() => {
      setPlayingIndex(null);
      setError('Could not play the stored audio for this turn.');
    });
  };

  const handleTimeUpdate = () => {
    const audio = audioRef.current;
    if (playingIndex === null || !audio) {
      return;
    }
    const turn = turns[playingIndex];
    if (turn && audio.currentTime >= turn.end) {
      audio.pause();
      setPlayingIndex(null);
    }
  };

  const saveTurnText = (index, text) => {
    setTurns((current) => current.map(
      (turn, position) => (position === index ? { ...turn, text } : turn),
    ));
  };

  const handleGenerateNote = async () => {
    const labelled = formatLabelledTranscript(turns, clinicianFirst);
    if (!labelled.trim()) {
      setError('The transcript is empty. Record or upload an encounter first.');
      return;
    }
    setStartingNote(true);
    setError(null);
    try {
      const job = await createSoap({ transcript: labelled, jobId });
      setSession((current) => ({
        ...current,
        transcript: labelled,
        sttJobId: jobId,
        soapJobId: job.soap_job_id,
        encounterId: job.encounter_id,
        soapNote: job.soap_note,
      }));
      go('generation');
    } catch (cause) {
      setError(cause.message);
    } finally {
      setStartingNote(false);
    }
  };

  // Generate Note takes a second row in the absolutely positioned footer, so
  // the panel above it needs extra clearance while it is showing.
  const showGenerate = status === 'ready' && turns.length > 0;

  const statusLabel = {
    idle: 'Ready',
    recording: 'Recording',
    processing: 'Transcribing',
    ready: 'Transcribed',
    error: 'Stopped',
  }[status];

  return (
    <div className={`recording-screen ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <AppSidebar active="review" go={go} collapsed={sidebarCollapsed} onToggle={onToggleSidebar} />
      <div className="recording-main">
        <TopBar title="Live Encounter" go={go} showBack />
        <main className={`recording-canvas ${showGenerate ? 'has-generate' : ''}`}>
          <aside className="recording-status">
            <div className="desktop-patient">
              <h2>Marcus Johnson</h2>
              <p>DOB: 11/04/1978 (45y)</p>
            </div>
            <div className={`record-timer ${status === 'recording' ? '' : 'idle'}`} aria-live="polite">
              <span className="record-dot" />
              <div>
                <b>{statusLabel}</b>
                <code>{formatClock(elapsed)}</code>
              </div>
            </div>
            <button type="button" className="button button-soft">
              <Icon name="flag" />
              Flag Moment
            </button>
          </aside>

          <section className="transcript-panel" aria-label="Encounter transcript">
            {turns.length > 1 ? (
              <div className="speaker-swap">
                <span>
                  {roles.size}
                  {' '}
                  speakers detected
                </span>
                <button
                  type="button"
                  className="button button-soft button-tiny"
                  onClick={() => setClinicianFirst((value) => !value)}
                >
                  <Icon name="sync" />
                  Swap speakers
                </button>
              </div>
            ) : null}

            {error ? (
              <div className="transcript-error" role="alert">
                <Icon name="error" />
                <p>{error}</p>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => {
                    setError(null);
                    if (status === 'error') {
                      setStatus(turns.length ? 'ready' : 'idle');
                    }
                  }}
                >
                  <Icon name="close" />
                </button>
              </div>
            ) : null}

            {turns.map((turn, index) => {
              const role = roles.get(turn.speaker_id) ?? 'patient';
              return (
                <TranscriptBubble
                  key={`${turn.speaker_id}-${turn.start}`}
                  speaker={role === 'clinician' ? CLINICIAN_LABEL : PATIENT_LABEL}
                  doctor={role === 'clinician'}
                  text={turn.text}
                  timeLabel={formatClock(turn.start)}
                  canPlay={Boolean(jobId)}
                  isPlaying={playingIndex === index}
                  editable
                  onPlay={() => playTurn(index)}
                  onEditSave={(text) => saveTurnText(index, text)}
                />
              );
            })}

            {status === 'processing' ? (
              <div className="transcript-processing">
                <div className="typing-bubble" aria-label="Transcribing">
                  <span />
                  <span />
                  <span />
                </div>
                <p>Transcribing and separating speakers…</p>
                <button type="button" className="button button-soft button-tiny" onClick={cancelProcessing}>
                  Cancel
                </button>
              </div>
            ) : null}

            {status === 'recording' ? (
              <div className="transcript-processing">
                <div className="typing-bubble" aria-label="Recording">
                  <span />
                  <span />
                  <span />
                </div>
                <p>Recording. The transcript appears when you end the encounter.</p>
              </div>
            ) : null}

            {turns.length === 0 && status !== 'processing' && status !== 'recording' ? (
              <div className="transcript-empty">
                <Icon name="mic" />
                <p>Start the encounter to record, or upload an existing audio file.</p>
              </div>
            ) : null}
          </section>

          <aside className="extraction-panel">
            <h2><Icon name="auto_awesome" filled />Live Extraction</h2>
            <ExtractionTag icon="pulmonology" type="Symptom" label="Chest tightness" tone="symptom" />
            <ExtractionTag icon="medication" type="Med" label="Lisinopril" tone="med" />
            <ExtractionTag icon="schedule" type="Onset" label="3 days ago" tone="time" />
          </aside>

          <footer className="recording-actions">
            {status === 'recording' ? (
              <button type="button" className="button button-danger" onClick={endEncounter}>
                <Icon name="stop_circle" filled />
                End Encounter
              </button>
            ) : (
              <button
                type="button"
                className="button button-primary"
                onClick={startEncounter}
                disabled={status === 'processing' || !recorder.isSupported}
                title={recorder.isSupported ? undefined : 'This browser cannot record audio'}
              >
                <Icon name="mic" filled />
                Start Encounter
              </button>
            )}

            <button
              type="button"
              className="button button-soft"
              onClick={() => fileInputRef.current?.click()}
              disabled={isBusy}
            >
              <Icon name="cloud_sync" />
              Upload
            </button>

            {showGenerate ? (
              <button
                type="button"
                className="button button-outline recording-generate"
                onClick={handleGenerateNote}
                disabled={startingNote}
              >
                <Icon name="auto_awesome" />
                {startingNote ? 'Starting…' : 'Generate Note'}
              </button>
            ) : null}

            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,.webm,.m4a,.opus"
              className="visually-hidden-input"
              onChange={handleFilePicked}
            />
          </footer>

          {jobId ? (
            <audio
              ref={audioRef}
              src={jobAudioUrl(jobId)}
              preload="metadata"
              hidden
              onTimeUpdate={handleTimeUpdate}
              onEnded={() => setPlayingIndex(null)}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}

export default RecordingScreen;
