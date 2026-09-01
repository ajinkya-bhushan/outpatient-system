import React from 'react';
import AppSidebar from '../components/AppSidebar.jsx';
import TopBar from '../components/TopBar.jsx';

function TransactionFrame({
  title,
  subtitle,
  go,
  children,
  footer,
  close = false,
  active = 'review',
  sidebarCollapsed,
  onToggleSidebar,
}) {
  return (
    <div className={`transaction-frame ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <AppSidebar active={active} go={go} collapsed={sidebarCollapsed} onToggle={onToggleSidebar} />
      <div className="transaction-main">
        <TopBar title={title} subtitle={subtitle} go={go} showBack={!close} showClose={close} />
        <main className="transaction-canvas">{children}</main>
      </div>
      {footer}
    </div>
  );
}

export default TransactionFrame;
