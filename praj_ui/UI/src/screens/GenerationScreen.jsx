import React, { useEffect, useState } from 'react';
import Icon from '../components/Icon.jsx';
import Step from '../components/Step.jsx';
import { patient } from '../data/clinicalData.js';
import TransactionFrame from '../layouts/TransactionFrame.jsx';

function GenerationScreen({ go, sidebarCollapsed, onToggleSidebar }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setReady(true), 1800);
    return () => window.clearTimeout(timer);
  }, []);

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
          ) : (
            <button type="button" className="button button-outline button-xl" onClick={() => go('recording')}>
              Cancel Processing
            </button>
          )}
        </footer>
      )}
    >
      <section className="generation-content">
        <div className="ai-ring" aria-hidden="true">
          <svg viewBox="0 0 100 100">
            <circle className="track" cx="50" cy="50" r="45" />
            <circle className="progress" cx="50" cy="50" r="45" />
          </svg>
          <span><Icon name="auto_awesome" filled /></span>
        </div>
        <div className="generation-copy">
          <h2>{patient.name}</h2>
          <p>AI is drafting your note. This usually takes 30-60 seconds.</p>
        </div>
        <section className="step-panel" aria-label="AI generation steps">
          <Step done title="Transcribing" detail="Audio successfully converted to text." />
          <Step active={!ready} done={ready} title="Extracting Clinical Entities" detail={ready ? 'Clinical concepts mapped to the chart.' : 'Identifying symptoms, medications, and onset.'} />
          <Step active={ready} title="Generating Note" detail={ready ? 'SOAP format ready for review.' : 'Structuring SOAP format...'} />
        </section>
      </section>
    </TransactionFrame>
  );
}

export default GenerationScreen;
