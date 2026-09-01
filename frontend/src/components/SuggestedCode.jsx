import React from 'react';
import Icon from './Icon.jsx';

function SuggestedCode({ code, label, selected = false, matched = false }) {
  return (
    <article className={`suggested-code ${selected ? 'selected' : ''}`}>
      <header>
        <span>ICD-10</span>
        {selected ? <Icon name="check_circle" /> : null}
      </header>
      <strong>{code}</strong>
      <p>{label}</p>
      {matched ? (
        <div className="code-match">
          <Icon name="info" />
          Match found in transcript
        </div>
      ) : null}
    </article>
  );
}

export default SuggestedCode;
