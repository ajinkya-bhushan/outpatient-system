import React from 'react';
import Icon from './Icon.jsx';
import StatusBadge from './StatusBadge.jsx';

function PatientCard({ appointment, onClick }) {
  return (
    <button type="button" className={`patient-card ${appointment.tone}`} onClick={onClick}>
      <span className="time">{appointment.time}</span>
      <span className="patient-card-body">
        <span className="patient-title-row">
          <strong>{appointment.name}</strong>
          <code>{appointment.meta}</code>
        </span>
        <span className="patient-reason">
          <Icon name={appointment.icon} />
          {appointment.reason}
        </span>
      </span>
      <StatusBadge tone={appointment.tone}>{appointment.status}</StatusBadge>
      <Icon name="chevron_right" className="chevron" />
    </button>
  );
}

export default PatientCard;
