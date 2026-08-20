import React from 'react';

function Avatar({ initials = 'JS', size = 'md', label = 'Physician profile' }) {
  return (
    <div aria-label={label} className={`avatar avatar-${size}`}>
      {initials}
    </div>
  );
}

export default Avatar;
