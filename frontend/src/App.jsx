import React, { useState } from 'react';
import { screens } from './data/clinicalData.js';
import ClinicalShell from './layouts/ClinicalShell.jsx';
import AnalyticsScreen from './screens/AnalyticsScreen.jsx';
import GenerationScreen from './screens/GenerationScreen.jsx';
import LoginScreen from './screens/LoginScreen.jsx';
import PreVisitScreen from './screens/PreVisitScreen.jsx';
import RecordingScreen from './screens/RecordingScreen.jsx';
import ReviewScreen from './screens/ReviewScreen.jsx';
import ScheduleScreen from './screens/ScheduleScreen.jsx';
import SyncScreen from './screens/SyncScreen.jsx';

function getInitialScreen() {
  if (typeof window === 'undefined') {
    return 'login';
  }

  const requested = new URLSearchParams(window.location.search).get('screen');
  return screens.includes(requested) ? requested : 'login';
}

function App() {
  const [screen, setScreen] = useState(getInitialScreen);
  const [role, setRole] = useState('Physician');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const toggleSidebar = () => setSidebarCollapsed((value) => !value);

  const go = (next) => {
    setScreen(next);
    if (typeof window !== 'undefined') {
      const url = next === 'login' ? window.location.pathname : `${window.location.pathname}?screen=${next}`;
      window.history.replaceState(null, '', url);
    }
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };

  const sidebarProps = {
    sidebarCollapsed,
    onToggleSidebar: toggleSidebar,
  };

  if (screen === 'login') {
    return <LoginScreen role={role} setRole={setRole} go={go} />;
  }

  if (screen === 'previsit') {
    return <PreVisitScreen go={go} {...sidebarProps} />;
  }

  if (screen === 'recording') {
    return <RecordingScreen go={go} {...sidebarProps} />;
  }

  if (screen === 'generation') {
    return <GenerationScreen go={go} {...sidebarProps} />;
  }

  if (screen === 'review') {
    return <ReviewScreen go={go} {...sidebarProps} />;
  }

  if (screen === 'sync') {
    return <SyncScreen go={go} {...sidebarProps} />;
  }

  return (
    <ClinicalShell active={screen} go={go} {...sidebarProps}>
      {screen === 'analytics' ? <AnalyticsScreen /> : <ScheduleScreen go={go} />}
    </ClinicalShell>
  );
}

export default App;
