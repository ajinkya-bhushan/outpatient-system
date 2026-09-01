import React from 'react';
import Icon from '../components/Icon.jsx';
import PatientCard from '../components/PatientCard.jsx';
import { appointments } from '../data/clinicalData.js';

function ScheduleScreen({ go }) {
  return (
    <div className="schedule-page">
      <div className="desktop-dashboard-grid">
        <div className="desktop-dashboard-main">
          <section className="page-heading">
            <div>
              <span className="page-eyebrow">Patient Dashboard</span>
              <h2>Today's Schedule</h2>
              <p>Aug 19, 2026 - 12 appointments</p>
            </div>
            <div className="filter-row" aria-label="Schedule filters">
              <button type="button" className="filter-pill selected">All Today</button>
              <button type="button" className="filter-pill">
                <span className="dot danger" />
                Needs Review
              </button>
              <button type="button" className="filter-pill">Synced</button>
            </div>
          </section>

          <section className="alert-banner" aria-labelledby="urgent-review">
            <Icon name="warning" />
            <div>
              <h3 id="urgent-review">2 Charts Need Immediate Review</h3>
              <p>Pending AI documentation for recent critical visits requires physician sign-off to maintain compliance.</p>
            </div>
          </section>

          <section className="patient-list" aria-label="Patient queue">
            {appointments.map((appointment, index) => (
              <PatientCard key={appointment.name} appointment={appointment} onClick={() => index === 0 ? go('previsit') : go('review')} />
            ))}
          </section>
        </div>

        <aside className="desktop-context-panel" aria-label="Today overview">
          <section className="context-card">
            <h3><Icon name="timer" />Clinic Flow</h3>
            <div className="metric-row"><span>On time</span><strong>83%</strong></div>
            <div className="metric-row"><span>Avg note draft</span><strong>0:42</strong></div>
            <div className="metric-row"><span>Open reviews</span><strong>2</strong></div>
          </section>
          <section className="context-card">
            <h3><Icon name="cloud_sync" />EHR Sync</h3>
            <p>Epic connection healthy. Last FHIR write completed 8 minutes ago.</p>
            <button type="button" className="review-text-button" onClick={() => go('sync')}>
              View Status
            </button>
          </section>
          <section className="context-card">
            <h3><Icon name="auto_awesome" />AI Queue</h3>
            <p>Three encounters have enough transcript signal for automatic SOAP draft generation.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default ScheduleScreen;
