import React from 'react';

function Accuracy({ label, value, accent = false }) {
  return (
    <div className="accuracy-row">
      <div>
        <span>{label}</span>
        <b>{value}%</b>
      </div>
      <div className="meter">
        <span className={accent ? 'accent' : ''} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default Accuracy;
