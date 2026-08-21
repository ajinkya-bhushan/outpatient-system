import React from 'react';
import AppSidebar from '../components/AppSidebar.jsx';
import BottomNav from '../components/BottomNav.jsx';
import TopBar from '../components/TopBar.jsx';

function ClinicalShell({ active, go, children, sidebarCollapsed, onToggleSidebar }) {
  return (
    <div className={`shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <AppSidebar
        active={active === 'analytics' ? 'analytics' : 'schedule'}
        go={go}
        collapsed={sidebarCollapsed}
        onToggle={onToggleSidebar}
      />

      <div className="shell-main">
        <TopBar title="DocConnect" go={go} active={active} />
        <main className="page-canvas">{children}</main>
      </div>
      <BottomNav active={active} go={go} />
    </div>
  );
}

export default ClinicalShell;
