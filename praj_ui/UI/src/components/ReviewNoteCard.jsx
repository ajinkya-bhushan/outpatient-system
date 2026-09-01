import React from 'react';
import Icon from './Icon.jsx';

function ReviewNoteCard({ title, icon, action, children }) {
  return (
    <section className="review-note-card">
      <header>
        <h2><Icon name={icon} />{title}</h2>
        {action}
      </header>
      <div className="review-note-body">{children}</div>
    </section>
  );
}

export default ReviewNoteCard;
