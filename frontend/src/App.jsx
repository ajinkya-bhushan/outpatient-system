import React, { useCallback, useState } from 'react';
import { getToken } from './api/auth.js';
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

const SESSION_KEY = 'docconnect_encounter_session';

function emptySession() {
  return {
    transcript: '',
    sttJobId: null,
    soapJobId: null,
    encounterId: null,
    soapNote: null,
  };
}

function readSession() {
  if (typeof window === 'undefined') {
    return emptySession();
  }
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    return raw ? { ...emptySession(), ...JSON.parse(raw) } : emptySession();
  } catch {
    return emptySession();
  }
}

function getInitialScreen() {
  if (typeof window === 'undefined') {
    return 'login';
  }

  const requested = new URLSearchParams(window.location.search).get('screen');
  if (!screens.includes(requested)) {
    return 'login';
  }
  if (requested !== 'login' && !getToken()) {
    return 'login';
  }
  return requested;
}

function App() {
  const [screen, setScreen] = useState(getInitialScreen);
  const [role, setRole] = useState('Physician');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [session, setSessionState] = useState(readSession);

  const setSession = useCallback((update) => {
    setSessionState((current) => {
      const next = typeof update === 'function' ? update(current) : { ...current, ...update };
      try {
        window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
      } catch {
        // Ignore quota / private-mode failures; in-memory session still works.
      }
      return next;
    });
  }, []);

  const toggleSidebar = () => setSidebarCollapsed((value) => !value);

  const go = (next) => {
    const target = next !== 'login' && !getToken() ? 'login' : next;
    setScreen(target);
    if (typeof window !== 'undefined') {
      const url = target === 'login' ? window.location.pathname : `${window.location.pathname}?screen=${target}`;
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
    return <RecordingScreen go={go} setSession={setSession} {...sidebarProps} />;
  }

  if (screen === 'generation') {
    return <GenerationScreen go={go} session={session} setSession={setSession} {...sidebarProps} />;
  }

  if (screen === 'review') {
    return <ReviewScreen go={go} session={session} setSession={setSession} {...sidebarProps} />;
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
