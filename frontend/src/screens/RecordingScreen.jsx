import React, { useEffect, useState } from 'react';
import AppSidebar from '../components/AppSidebar.jsx';
import ExtractionTag from '../components/ExtractionTag.jsx';
import Icon from '../components/Icon.jsx';
import TopBar from '../components/TopBar.jsx';
import TranscriptBubble from '../components/TranscriptBubble.jsx';

function RecordingScreen({ go, sidebarCollapsed, onToggleSidebar }) {
  const [seconds, setSeconds] = useState(252);

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
  const rest = String(seconds % 60).padStart(2, '0');

  return (
    <div className={`recording-screen ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <AppSidebar active="review" go={go} collapsed={sidebarCollapsed} onToggle={onToggleSidebar} />
      <div className="recording-main">
        <TopBar title="Live Encounter" go={go} showBack />
        <main className="recording-canvas">
          <aside className="recording-status">
            <div className="desktop-patient">
              <h2>Marcus Johnson</h2>
              <p>DOB: 11/04/1978 (45y)</p>
            </div>
            <div className="record-timer" aria-live="polite">
              <span className="record-dot" />
              <div>
                <b>Recording</b>
                <code>{minutes}:{rest}</code>
              </div>
            </div>
            <button type="button" className="button button-soft">
              <Icon name="flag" />
              Flag Moment
            </button>
          </aside>

          <section className="transcript-panel" aria-label="Live transcript">
            <TranscriptBubble speaker="Marcus">
              Yeah, it started about three days ago. Just a tight feeling, mostly when I try to take a deep breath or climb the stairs.
            </TranscriptBubble>
            <TranscriptBubble speaker="Dr. Smith" doctor>
              I see. Does the tightness spread anywhere else? Like your arm, neck, or jaw?
            </TranscriptBubble>
            <TranscriptBubble speaker="Marcus">
              No, not really spreading. It just stays right in the center. I did take my Lisinopril this morning though.
            </TranscriptBubble>
            <div className="typing-bubble" aria-label="Listening">
              <span />
              <span />
              <span />
            </div>
          </section>

          <aside className="extraction-panel">
            <h2><Icon name="auto_awesome" filled />Live Extraction</h2>
            <ExtractionTag icon="pulmonology" type="Symptom" label="Chest tightness" tone="symptom" />
            <ExtractionTag icon="medication" type="Med" label="Lisinopril" tone="med" />
            <ExtractionTag icon="schedule" type="Onset" label="3 days ago" tone="time" />
          </aside>

          <footer className="recording-actions">
            <button type="button" className="button button-soft">
              <Icon name="pause" />
              Pause
            </button>
            <button type="button" className="button button-danger" onClick={() => go('generation')}>
              <Icon name="stop_circle" filled />
              End Encounter
            </button>
          </footer>
        </main>
      </div>
    </div>
  );
}

export default RecordingScreen;
