import React, { useState } from 'react';
import AppSidebar from '../components/AppSidebar.jsx';
import Icon from '../components/Icon.jsx';
import ReviewNoteCard from '../components/ReviewNoteCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import SuggestedCode from '../components/SuggestedCode.jsx';
import { patient } from '../data/clinicalData.js';

function ReviewScreen({ go, sidebarCollapsed, onToggleSidebar }) {
  const [planAccepted, setPlanAccepted] = useState(false);
  const [plan, setPlan] = useState([
    '- Continue Lisinopril 20mg PO daily.',
    '- Emphasized the importance of continued dietary sodium restriction and regular aerobic exercise.',
    '- Advised patient to continue home blood pressure monitoring and keep a log.',
    '- Re-check Basic Metabolic Panel (BMP) to monitor renal function and potassium levels.',
    '- Regarding muscle aches, will hold Atorvastatin for 2 weeks to see if symptoms resolve, then reconsider rechallenge or alternative agent.',
  ].join('\n'));

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
            <span>AI draft ready for review</span>
            <h2>{patient.name}</h2>
            <p>Cardiology Follow-up - MRN {patient.mrn} - Aug 19, 2026</p>
          </div>
          <StatusBadge tone="urgent">Needs physician review</StatusBadge>
        </section>

        <ReviewNoteCard
          title="Subjective"
          icon="chat_bubble"
          action={(
            <button type="button" className="review-text-button">
              <Icon name="mic" />
              Transcript
            </button>
          )}
        >
          <p>
            Patient presents for cardiology follow-up. Reports improved exercise tolerance since last visit, but still notes intermittent fatigue in the evenings. Denies shortness of breath at rest, palpitations, syncope, or dizziness.
          </p>
          <div className="review-verify-block">
            <span><Icon name="warning" />Verify patient wording</span>
            <p>Single episode of mild chest tightness while climbing stairs yesterday, lasting approximately 2 minutes and resolving with rest.</p>
          </div>
        </ReviewNoteCard>

        <ReviewNoteCard title="Assessment" icon="monitor_heart">
          <ol className="review-assessment-list">
            <li>
              <strong>Essential Hypertension (I10)</strong>
              <p>Improved but not yet at target. Home blood pressure log shows readings averaging 132-138 systolic.</p>
            </li>
            <li>
              <strong>Hyperlipidemia (E78.5)</strong>
              <p>Stable on Atorvastatin.</p>
              <div className="review-verify-block compact">
                <span><Icon name="info" />Match found in transcript</span>
                <p>Patient noted mild muscle aches in legs, possibly statin-related, though recent CK levels were normal.</p>
              </div>
            </li>
          </ol>
        </ReviewNoteCard>

        <ReviewNoteCard
          title="Plan"
          icon="description"
          action={(
            <div className="review-card-actions">
              <button type="button" aria-label="Regenerate plan" className="icon-button">
                <Icon name="sync" />
              </button>
              <button type="button" className={`review-accept-button ${planAccepted ? 'accepted' : ''}`} onClick={() => setPlanAccepted(true)}>
                {planAccepted ? 'Accepted' : 'Accept'}
              </button>
            </div>
          )}
        >
          <textarea
            aria-label="Edit plan"
            className="review-plan-editor"
            value={plan}
            onChange={(event) => {
              setPlanAccepted(false);
              setPlan(event.target.value);
            }}
          />
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
        <button type="button" className="button button-primary button-xl" onClick={() => go('sync')}>
          <Icon name="cloud_sync" />
          Approve &amp; Sync
        </button>
      </footer>
    </div>
  );
}

export default ReviewScreen;
