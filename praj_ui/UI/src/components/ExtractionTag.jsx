import React from 'react';
import Icon from './Icon.jsx';

function ExtractionTag({ icon, type, label, tone }) {
  return (
    <button type="button" className={`extraction-tag ${tone}`}>
      <Icon name={icon} />
      <span>
        <b>{type}</b>
        {label}
      </span>
    </button>
  );
}

export default ExtractionTag;
