import React from 'react';
import { desktopNavItems } from '../data/clinicalData.js';
import Avatar from './Avatar.jsx';
import Icon from './Icon.jsx';

function AppSidebar({ active, go, collapsed = false, onToggle }) {
  const toggleLabel = collapsed ? 'Expand navigation' : 'Collapse navigation';

  return (
    <aside className={`app-sidebar ${collapsed ? 'collapsed' : ''}`} aria-label="Clinical workspace navigation">
      <button
        type="button"
        className="icon-button sidebar-toggle"
        aria-label={toggleLabel}
        aria-expanded={!collapsed}
        title={toggleLabel}
        onClick={onToggle}
      >
        <Icon name={collapsed ? 'chevron_right' : 'chevron_left'} />
      </button>
      <div className="app-clinician">
        <Avatar initials="DS" size="lg" />
        <div className="app-clinician-details">
          <h1>Dr. Smith</h1>
          <p>Cardiology Dept.</p>
          <code>MRN: 882-194</code>
        </div>
      </div>
      <nav className="app-nav">
        {desktopNavItems.map((item) => (
          <button
            key={item.label}
            type="button"
            className={active === item.key ? 'active' : ''}
            onClick={() => item.key !== 'settings' && go(item.key)}
            aria-label={item.label}
            title={collapsed ? item.label : undefined}
          >
            <Icon name={item.icon} />
            <span className="app-nav-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

export default AppSidebar;
