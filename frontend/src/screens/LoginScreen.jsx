import React, { useState } from 'react';
import { login as loginRequest } from '../api/auth.js';
import Icon from '../components/Icon.jsx';

function LoginScreen({ role, setRole, go }) {
  const [providerId, setProviderId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await loginRequest({
        provider_id: providerId,
        password,
        role,
      });
      go('schedule');
    } catch (err) {
      if (err.status === 401) {
        setError(err.message || 'Invalid provider ID or password');
      } else {
        setError('Unable to sign in. Check your connection and try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-screen">
      <section className="login-intro">
        <div className="brand-mark">
          <Icon name="local_hospital" filled />
        </div>
        <h1>DocConnect</h1>
        <p>AI-assisted clinical documentation workspace for cardiology teams.</p>
        <div className="login-proof-grid">
          <span><Icon name="security" />HIPAA-ready session controls</span>
          <span><Icon name="cloud_sync" />Epic EHR synchronization</span>
          <span><Icon name="auto_awesome" />AI SOAP note drafting</span>
        </div>
      </section>
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-mark">
          <Icon name="local_hospital" filled />
        </div>
        <div className="login-heading">
          <h1 id="login-title">DocConnect</h1>
          <p>Secure Clinical Portal</p>
        </div>

        {error ? (
          <div className="login-error-pop" role="alert">
            <Icon name="error" />
            <div>
              <strong>Sign in failed</strong>
              <p>{error}</p>
            </div>
            <button
              type="button"
              className="login-error-dismiss"
              onClick={() => setError('')}
              aria-label="Dismiss error"
            >
              <Icon name="close" />
            </button>
          </div>
        ) : null}

        <div className="segment" role="group" aria-label="Clinical role">
          {['Physician', 'Admin'].map((item) => (
            <button
              type="button"
              aria-pressed={role === item}
              className={role === item ? 'selected' : ''}
              key={item}
              onClick={() => setRole(item)}
            >
              {item}
            </button>
          ))}
        </div>

        <button type="button" className="button button-primary button-xl">
          <Icon name="login" />
          Sign in with Hospital SSO
        </button>

        <div className="divider">
          <span />
          <b>OR</b>
          <span />
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            <span>Provider ID</span>
            <div className="input-wrap">
              <Icon name="badge" />
              <input
                placeholder="Enter Provider ID"
                autoComplete="username"
                value={providerId}
                onChange={(event) => setProviderId(event.target.value)}
                required
              />
            </div>
          </label>
          <label>
            <span className="row-between">
              <span>Password</span>
              <a href="#forgot">Forgot?</a>
            </span>
            <div className="input-wrap">
              <Icon name="lock" />
              <input
                placeholder="Enter Password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
          </label>
          <button
            type="submit"
            className="button button-outline button-xl"
            disabled={submitting}
          >
            {submitting ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <footer className="hipaa-note">
          <Icon name="security" filled />
          <div>
            <h2>HIPAA Compliant System</h2>
            <p>
              For your security, this session will automatically lock after 5 minutes of inactivity. Ensure you are in a private area before viewing patient data.
            </p>
          </div>
        </footer>
      </section>
    </main>
  );
}

export default LoginScreen;
