import React from 'react';

function TranscriptBubble({ speaker, doctor = false, children }) {
  return (
    <article className={`transcript-bubble ${doctor ? 'doctor' : ''}`}>
      <span>{speaker}</span>
      <p>{children}</p>
    </article>
  );
}

export default TranscriptBubble;
