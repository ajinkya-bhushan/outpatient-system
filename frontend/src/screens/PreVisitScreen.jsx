import React from 'react';
import Avatar from '../components/Avatar.jsx';
import Icon from '../components/Icon.jsx';
import { labs, medications, patient } from '../data/clinicalData.js';
import TransactionFrame from '../layouts/TransactionFrame.jsx';

function PreVisitScreen({ go, sidebarCollapsed, onToggleSidebar }) {
  return (
    <TransactionFrame
      title="Pre-Visit Dashboard"
      go={go}
      active="previsit"
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={onToggleSidebar}
      footer={(
        <footer className="sticky-footer">
          <button type="button" className="button button-primary button-xl" onClick={() => go('recording')}>
            <Icon name="play_arrow" filled />
            Start Encounter
          </button>
        </footer>
      )}
    >
      <div className="previsit-workgrid">
        <div className="previsit-main">
          <section className="patient-summary">
            <Avatar initials="MT" size="xl" label="Marcus Thorne" />
            <div>
              <span className="page-eyebrow">Next encounter</span>
              <h2>{patient.name}</h2>
              <div className="metadata-row">
                <span><Icon name="calendar_month" />{patient.age}</span>
                <span><Icon name="badge" />MRN: <code>{patient.mrn}</code></span>
                <span><Icon name="male" />{patient.sex}</span>
              </div>
            </div>
          </section>

          <div className="clinical-grid">
            <section className="clinical-panel complaint-panel">
              <h3><Icon name="chat_bubble" />Chief Complaint</h3>
              <p className="quote">"Chest tightness, intermittent"</p>
              <p>Duration: 3 days. Worse with exertion.</p>
            </section>
            <section className="clinical-panel allergy-panel">
              <h3><Icon name="warning" filled />Allergies</h3>
              <strong>Penicillin</strong>
              <p>Reaction: Anaphylaxis</p>
            </section>
          </div>

          <section className="clinical-panel table-panel">
            <header>
              <h3><Icon name="science" />Recent Labs</h3>
              <span>Drawn 2 days ago</span>
            </header>
            <div className="lab-list">
              {labs.map((lab) => (
                <div key={lab.name} className={`lab-row ${lab.tone}`}>
                  <div>
                    <strong>{lab.name}</strong>
                    <span>{lab.detail}</span>
                  </div>
                  <div className="lab-value">
                    <code>{lab.value}</code>
                    <b>{lab.status}</b>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="clinical-panel table-panel">
            <header>
              <h3><Icon name="pill" />Active Medications</h3>
            </header>
            <div className="med-list">
              {medications.map(([name, dose]) => (
                <button type="button" key={name} className="med-row">
                  <Icon name="medication" />
                  <span>
                    <strong>{name}</strong>
                    <small>{dose}</small>
                  </span>
                  <Icon name="chevron_right" />
                </button>
              ))}
            </div>
          </section>

          <button type="button" className="history-panel">
            <span><Icon name="history" />Past Medical History</span>
            <span>HTN, Hyperlipidemia, Type 2 DM <Icon name="expand_more" /></span>
          </button>
        </div>

        <aside className="previsit-rail">
          <section className="context-card">
            <h3><Icon name="warning" />Safety Flags</h3>
            <p>Penicillin anaphylaxis. HbA1c abnormal at 7.2%.</p>
          </section>
          <section className="context-card">
            <h3><Icon name="monitor_heart" />Visit Focus</h3>
            <div className="metric-row"><span>Chest symptoms</span><strong>High</strong></div>
            <div className="metric-row"><span>Diabetes control</span><strong>Review</strong></div>
            <div className="metric-row"><span>Medication adherence</span><strong>Ask</strong></div>
          </section>
          <section className="context-card">
            <h3><Icon name="mic" />Recording Prep</h3>
            <p>Ambient capture will extract symptoms, meds, labs, and plan changes in real time.</p>
          </section>
        </aside>
      </div>
    </TransactionFrame>
  );
}

export default PreVisitScreen;
