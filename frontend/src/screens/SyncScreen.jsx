import React from 'react';
import Icon from '../components/Icon.jsx';
import ResourceRow from '../components/ResourceRow.jsx';
import { patient } from '../data/clinicalData.js';
import TransactionFrame from '../layouts/TransactionFrame.jsx';

function SyncScreen({ go, sidebarCollapsed, onToggleSidebar }) {
  return (
    <TransactionFrame
      title="EHR Sync Status"
      go={go}
      active="schedule"
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={onToggleSidebar}
    >
      <section className="success-content">
        <div className="success-mark">
          <svg viewBox="0 0 24 24">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </div>
        <h1>Sync Successful</h1>
        <p>
          Note successfully written to Epic EHR for {patient.name} <code>(MRN {patient.mrn})</code>
        </p>
      </section>

      <section className="resource-panel">
        <header>
          <Icon name="data_object" />
          <h2>FHIR Resources Updated</h2>
        </header>
        <ResourceRow icon="event" title="Encounter" detail="Outpatient visit record created." />
        <ResourceRow icon="coronavirus" title="Condition" detail="Essential hypertension added to active problems." />
        <ResourceRow icon="prescriptions" title="MedicationRequest" detail="Lisinopril 10mg daily queued for pharmacy." />
      </section>

      <section className="success-actions">
        <button type="button" className="button button-primary button-xl" onClick={() => go('schedule')}>
          <Icon name="calendar_today" />
          Back to Schedule
        </button>
        <button type="button" className="button button-outline button-xl">
          <Icon name="description" />
          View Patient Instructions
        </button>
      </section>
    </TransactionFrame>
  );
}

export default SyncScreen;
