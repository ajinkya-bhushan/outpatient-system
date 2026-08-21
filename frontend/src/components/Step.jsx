import React from 'react';
import Icon from './Icon.jsx';

function Step({ title, detail, done = false, active = false }) {
  return (
    <div className={`step ${done ? 'done' : ''} ${active ? 'active' : ''}`}>
      <span className="step-marker">
        {done ? <Icon name="check" /> : active ? <Icon name="progress_activity" /> : null}
      </span>
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
    </div>
  );
}

export default Step;
