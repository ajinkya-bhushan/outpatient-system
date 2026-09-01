import React, { useEffect, useState } from 'react';
import { createSoap, getSoapNoteForEncounter, sectionText } from '../api/soap.js';
import AppSidebar from '../components/AppSidebar.jsx';
import Icon from '../components/Icon.jsx';
import ReviewNoteCard from '../components/ReviewNoteCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import SuggestedCode from '../components/SuggestedCode.jsx';
import { patient } from '../data/clinicalData.js';

function ReviewScreen({ go, session, setSession, sidebarCollapsed, onToggleSidebar }) {
  const [planAccepted, setPlanAccepted] = useState(false);
  const [editingPlan, setEditingPlan] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [soapNote, setSoapNote] = useState(session.soapNote);
  const [plan, setPlan] = useState(sectionText(session.soapNote, 'plan'));

  useEffect(() => {
    setSoapNote(session.soapNote);
    setPlan(sectionText(session.soapNote, 'plan'));
    setPlanAccepted(false);
    setEditingPlan(false);
  }, [session.soapNote]);

  useEffect(() => {
    if (session.soapNote || !session.encounterId) {
      return undefined;
    }
    const controller = new AbortController();
    getSoapNoteForEncounter(session.encounterId, { signal: controller.signal })
      .then((note) => {
        setSoapNote(note);
        setPlan(sectionText(note, 'plan'));
        setSession((current) => ({ ...current, soapNote: note }));
      })
      .catch((cause) => {
        if (cause.name !== 'AbortError') {
          setLoadError(cause.message);
        }
      });
    return () => controller.abort();
  }, [session.soapNote, session.encounterId, setSession]);

  const regenerate = async () => {
    if (!session.transcript) {
      go('generation');
      return;
    }
    setRegenerating(true);
    setLoadError(null);
    try {
      const job = await createSoap({
        transcript: session.transcript,
        jobId: session.sttJobId,
        encounterId: session.encounterId,
      });
      setSession((current) => ({
        ...current,
        soapJobId: job.soap_job_id,
        encounterId: job.encounter_id,
        soapNote: job.soap_note,
      }));
      go('generation');
    } catch (cause) {
      setLoadError(cause.message);
    } finally {
      setRegenerating(false);
    }
  };

  const subjective = sectionText(soapNote, 'subjective');
  const objective = sectionText(soapNote, 'objective');
  const assessment = sectionText(soapNote, 'assessment');
  const emptyDraft = !soapNote && !loadError;

  return (
    <div className={`review-workspace ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <AppSidebar active="review" go={go} collapsed={sidebarCollapsed} onToggle={onToggleSidebar} />

      <main className="review-document">
        <header className="review-mobile-header">
          <button type="button" className="icon-button" aria-label="Back to schedule" onClick={() => go('schedule')}>
            <Icon name="arrow_back" />
          </button>
          <div>
            <h1>Clinical History</h1>
            <p>{patient.name} - {patient.visit}</p>
          </div>
        </header>

        <section className="review-patient-banner">
          <div>
            <span>{soapNote ? 'AI draft ready for review' : 'No SOAP draft yet'}</span>
            <h2>{patient.name}</h2>
            <p>Cardiology Follow-up - MRN {patient.mrn} - Aug 19, 2026</p>
          </div>
          <StatusBadge tone={soapNote ? 'urgent' : 'neutral'}>
            {soapNote ? 'Needs physician review' : 'Waiting for draft'}
          </StatusBadge>
        </section>

        {loadError ? (
          <p className="review-load-error" role="alert">{loadError}</p>
        ) : null}

        {emptyDraft ? (
          <p className="review-empty-hint">
            Generate a note from a recorded encounter to review the SOAP draft here.
          </p>
        ) : null}

        <ReviewNoteCard
          title="Subjective"
          icon="chat_bubble"
          markdown={subjective || 'No subjective section in this draft.'}
          action={(
            <button
              type="button"
              className={`review-text-button ${showTranscript ? 'active' : ''}`}
              onClick={() => setShowTranscript((value) => !value)}
              disabled={!session.transcript}
            >
              <Icon name="mic" />
              Transcript
            </button>
          )}
        >
          {showTranscript && session.transcript ? (
            <div className="review-transcript-block">
              <span><Icon name="mic" />Source transcript</span>
              <pre>{session.transcript}</pre>
            </div>
          ) : null}
        </ReviewNoteCard>

        <ReviewNoteCard
          title="Objective"
          icon="stethoscope"
          markdown={objective || 'No objective section in this draft.'}
        />

        <ReviewNoteCard
          title="Assessment"
          icon="monitor_heart"
          markdown={assessment || 'No assessment section in this draft.'}
        />

        <ReviewNoteCard
          title="Plan"
          icon="description"
          markdown={editingPlan ? undefined : (plan || 'No plan section in this draft.')}
          action={(
            <div className="review-card-actions">
              <button
                type="button"
                aria-label="Regenerate plan"
                className="icon-button"
                onClick={regenerate}
                disabled={!session.transcript || regenerating}
              >
                <Icon name="sync" />
              </button>
              <button
                type="button"
                className={`review-text-button ${editingPlan ? 'active' : ''}`}
                onClick={() => setEditingPlan((value) => !value)}
              >
                <Icon name={editingPlan ? 'check' : 'edit'} />
                {editingPlan ? 'Done' : 'Edit'}
              </button>
              <button
                type="button"
                className={`review-accept-button ${planAccepted ? 'accepted' : ''}`}
                onClick={() => {
                  setEditingPlan(false);
                  setPlanAccepted(true);
                }}
                disabled={!plan}
              >
                {planAccepted ? 'Accepted' : 'Accept'}
              </button>
            </div>
          )}
        >
          {editingPlan ? (
            <textarea
              aria-label="Edit plan"
              className="review-plan-editor"
              value={plan}
              autoFocus
              onChange={(event) => {
                setPlanAccepted(false);
                setPlan(event.target.value);
              }}
            />
          ) : null}
        </ReviewNoteCard>
      </main>

      <aside className="review-code-rail" aria-label="Suggested codes">
        <section className="review-codes-panel">
          <h2><Icon name="badge" />Suggested Codes</h2>
          <SuggestedCode code="I10" label="Essential (primary) hypertension" matched selected />
          <SuggestedCode code="E78.5" label="Hyperlipidemia, unspecified" />
          <button type="button" className="add-code-button">
            <Icon name="add_circle" />
            Add Code
          </button>
        </section>
      </aside>

      <footer className="review-sync-bar">
        <button type="button" className="button button-outline" onClick={() => go('schedule')}>
          Save as Draft
        </button>
        <button type="button" className="button button-primary button-xl" onClick={() => go('sync')} disabled={!soapNote}>
          <Icon name="cloud_sync" />
          Approve &amp; Sync
        </button>
      </footer>
    </div>
  );
}

export default ReviewScreen;
