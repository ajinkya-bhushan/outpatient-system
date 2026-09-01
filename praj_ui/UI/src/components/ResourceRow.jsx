import React from 'react';
import Icon from './Icon.jsx';

function ResourceRow({ icon, title, detail }) {
  return (
    <div className="resource-row">
      <span><Icon name={icon} /></span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <Icon name="check_circle" filled />
    </div>
  );
}

export default ResourceRow;
