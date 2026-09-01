import React from 'react';
import Accuracy from '../components/Accuracy.jsx';
import Icon from '../components/Icon.jsx';
import { analyticsKpis } from '../data/clinicalData.js';

function AnalyticsScreen() {
  return (
    <div className="analytics-page">
      <section className="page-heading">
        <div>
          <h2>Clinical Impact Dashboard</h2>
          <p>Monitor workflow efficiency and documentation quality driven by AI assistance.</p>
        </div>
      </section>

      <section className="kpi-grid">
        {analyticsKpis.map(([icon, label, value, unit, helper]) => (
          <article key={label} className="kpi-card">
            <p><Icon name={icon} />{label}</p>
            <strong>{value}<span>{unit}</span></strong>
            {helper ? <small><Icon name="trending_up" />{helper}</small> : <div className="mini-meter"><span style={{ width: value }} /></div>}
          </article>
        ))}
      </section>

      <div className="analytics-grid">
        <section className="chart-panel">
          <header>
            <h2>Documentation Time Trends</h2>
            <div className="mini-tabs">
              <button type="button" className="active">Weekly</button>
              <button type="button">Monthly</button>
            </div>
          </header>
          <div className="chart-area">
            <div className="y-axis">
              <span>15</span>
              <span>10</span>
              <span>5</span>
              <span>0</span>
            </div>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Documentation time trend">
              <defs>
                <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="currentColor" stopOpacity="0.24" />
                  <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d="M0,80 Q10,75 20,60 T40,50 T60,30 T80,20 T100,10" fill="none" stroke="currentColor" strokeWidth="2" />
              <path d="M0,80 Q10,75 20,60 T40,50 T60,30 T80,20 T100,10 L100,100 L0,100 Z" fill="url(#trendFill)" />
              {[0, 20, 40, 60, 80, 100].map((x, index) => (
                <circle key={x} cx={x} cy={[80, 60, 50, 30, 20, 10][index]} r="1.6" fill="currentColor" />
              ))}
            </svg>
            <div className="x-axis">
              <span>Wk1</span>
              <span>Wk2</span>
              <span>Wk3</span>
              <span>Wk4</span>
              <span>Wk5</span>
              <span>Wk6</span>
            </div>
          </div>
        </section>

        <section className="breakdown-panel">
          <h2>Accuracy by Section</h2>
          <p>AI confidence across SOAP note sections.</p>
          <Accuracy label="Subjective (HPI)" value={96} />
          <Accuracy label="Objective (Vitals/Exam)" value={99} />
          <Accuracy label="Assessment" value={88} accent />
          <Accuracy label="Plan (Orders/Meds)" value={94} />
          <Accuracy label="Coding (ICD-10)" value={92} accent />
        </section>
      </div>
    </div>
  );
}

export default AnalyticsScreen;
