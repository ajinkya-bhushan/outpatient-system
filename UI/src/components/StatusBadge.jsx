import React from 'react';
import Icon from './Icon.jsx';

function StatusBadge({ tone, children }) {
  const icon = tone === 'done' ? 'cloud_done' : tone === 'urgent' ? 'error' : 'schedule';
  return (
    <span className={`status-badge ${tone}`}>
      <Icon name={icon} />
      {children}
    </span>
  );
}

export default StatusBadge;
