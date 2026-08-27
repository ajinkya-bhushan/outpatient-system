import React, { useEffect, useState } from 'react';
import { createSoap, getSoapJob, POLL_MS } from '../api/soap.js';
import Icon from '../components/Icon.jsx';
import Step from '../components/Step.jsx';
import { patient } from '../data/clinicalData.js';
import TransactionFrame from '../layouts/TransactionFrame.jsx';

const STEP_COPY = {
  transcribing: {
    title: 'Transcribing',
    done: 'Audio successfully converted to text.',
    active: 'Audio successfully converted to text.',
    queued: 'Waiting to start.',
    failed: 'Transcription was not available.',
  },
  extracting: {
    title: 'Extracting Clinical Entities',
    done: 'Clinical concepts mapped to the chart.',
    active: 'Identifying symptoms, medications, and onset.',
    queued: 'Waiting for entity extraction.',
    failed: 'Could not extract clinical entities.',
  },
  generating: {
    title: 'Generating Note',
    done: 'SOAP format ready for review.',
    active: 'Structuring SOAP format...',
    queued: 'Waiting to draft the note.',
    failed: 'Could not generate the SOAP draft.',
  },
};

function stepState(steps, id) {
  return steps?.find((step) => step.id === id)?.status || 'queued';
}

function GenerationScreen({
  go,
  session,
  setSession,
  sidebarCollapsed,
  onToggleSidebar,
}) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [retrying, setRetrying] = useState(false);

  const status = job?.status || (session.soapJobId ? 'queued' : null);
  const ready = status === 'done';
  const failed = status === 'failed' || Boolean(error);
  const steps = job?.steps || [
    { id: 'transcribing', status: 'done' },
    { id: 'extracting', status: session.soapJobId ? 'queued' : 'queued' },
    { id: 'generating', status: 'queued' },
  ];

  useEffect(() => {
    if (!session.soapJobId) {
      return undefined;
    }

    const controller = new AbortController();
    let timer;
    let cancelled = false;

    async function applyJob(next) {
      if (cancelled) {
        return;
      }
      setJob(next);
      setSession((current) => ({
        ...current,
        soapJobId: next.soap_job_id,
        encounterId: next.encounter_id,
        soapNote: next.soap_note || current.soapNote,
      }));
      if (next.status === 'failed') {
        setError(next.error?.detail || 'SOAP generation failed.');
      }
    }

    async function poll() {
      setError(null);
      try {
        let current = await getSoapJob(session.soapJobId, { signal: controller.signal });
        await applyJob(current);
        while (!cancelled && current.status !== 'done' && current.status !== 'failed') {
          await new Promise((resolve) => {
            timer = window.setTimeout(resolve, POLL_MS);
          });
          if (cancelled) {
            return;
          }
          current = await getSoapJob(current.soap_job_id, { signal: controller.signal });
          await applyJob(current);
        }
      } catch (cause) {
        if (cause.name === 'AbortError' || cancelled) {
          return;
        }
        setError(cause.message);
      }
    }

    poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [session.soapJobId, setSession]);

  const retry = async () => {
    if (!session.transcript) {
      go('recording');
      return;
    }
    setRetrying(true);
    setError(null);
    setJob(null);
    try {
      const next = await createSoap({
        transcript: session.transcript,
        jobId: session.sttJobId,
        encounterId: session.encounterId,
      });
      setSession((current) => ({
        ...current,
        soapJobId: next.soap_job_id,
        encounterId: next.encounter_id,
        soapNote: next.soap_note,
      }));
      setJob(next);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setRetrying(false);
    }
  };

  const copy = failed
    ? (error || 'SOAP generation failed.')
    : ready
      ? 'Draft ready for review.'
      : session.soapJobId
        ? 'AI is drafting your note. This usually takes 30-60 seconds.'
        : 'Start from a recorded encounter to generate a note.';

  return (
    <TransactionFrame
      title="AI Note Generation"
      go={go}
      close
      active="review"
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={onToggleSidebar}
      footer={(
        <footer className="sticky-footer generation-footer">
          {ready ? (
            <button type="button" className="button button-primary button-xl" onClick={() => go('review')}>
              <Icon name="description" />
              Review Draft Note
            </button>
          ) : failed || !session.soapJobId ? (
            <div className="generation-footer-actions">
              <button
                type="button"
                className="button button-primary button-xl"
                onClick={retry}
                disabled={!session.transcript || retrying}
              >
                <Icon name="sync" />
                {retrying ? 'Starting…' : 'Retry'}
              </button>
              <button type="button" className="button button-outline button-xl" onClick={() => go('recording')}>
                Back to Recording
              </button>
            </div>
          ) : (
            <button type="button" className="button button-outline button-xl" onClick={() => go('recording')}>
              Cancel Processing
            </button>
          )}
        </footer>
      )}
    >
      <section className="generation-content">
        <div className={`ai-ring ${ready || failed ? 'done' : ''}`} aria-hidden="true">
          <svg viewBox="0 0 100 100">
            <circle className="track" cx="50" cy="50" r="45" />
            <circle className="progress" cx="50" cy="50" r="45" />
          </svg>
          <span><Icon name="auto_awesome" filled /></span>
        </div>
        <div className="generation-copy">
          <h2>{patient.name}</h2>
          <p>{copy}</p>
        </div>
        {failed && error ? (
          <p className="generation-error" role="alert">{error}</p>
        ) : null}
        <section className="step-panel" aria-label="AI generation steps">
          {['transcribing', 'extracting', 'generating'].map((id) => {
            const state = stepState(steps, id);
            const labels = STEP_COPY[id];
            return (
              <Step
                key={id}
                title={labels.title}
                detail={labels[state] || labels.queued}
                done={state === 'done'}
                active={state === 'active'}
              />
            );
          })}
        </section>
      </section>
    </TransactionFrame>
  );
}

export default GenerationScreen;
