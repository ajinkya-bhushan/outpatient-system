import React from 'react';
import Avatar from './Avatar.jsx';
import Icon from './Icon.jsx';

function TopBar({ title, subtitle, go, showBack = false, showClose = false, active }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        {showBack || showClose ? (
          <button type="button" aria-label={showClose ? 'Close' : 'Back'} className="icon-button" onClick={() => go('schedule')}>
            <Icon name={showClose ? 'close' : 'arrow_back'} />
          </button>
        ) : (
          <Avatar initials="JS" size="sm" />
        )}
        <div>
          <h1>{title}</h1>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      <button type="button" aria-label="Verified user" className="icon-button shield-button" onClick={() => active === 'analytics' ? go('schedule') : undefined}>
        <Icon name="verified_user" filled />
      </button>
    </header>
  );
}

export default TopBar;
