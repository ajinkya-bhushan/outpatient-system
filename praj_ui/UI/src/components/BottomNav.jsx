import React from 'react';
import { navItems } from '../data/clinicalData.js';
import Icon from './Icon.jsx';

function BottomNav({ active, go }) {
  return (
    <nav className="bottom-nav" aria-label="Mobile navigation">
      {navItems.map((item) => {
        const isActive = item.key === active || (active === 'schedule' && item.preferredActive);
        return (
          <button key={`${item.label}-${item.key}`} type="button" className={isActive ? 'active' : ''} onClick={() => go(item.key)}>
            <Icon name={item.icon} filled={isActive} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export default BottomNav;
