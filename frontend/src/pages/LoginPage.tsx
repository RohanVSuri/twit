import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useMutation } from '@apollo/client/react';
import type { TwitterLoginMutation, TwitterLoginMutationVariables } from '@/types/__generated__/graphql';
import { TWITTER_LOGIN } from '@/operations/timeline';
import styles from '@/styles/LoginPage.module.css';

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [ct0, setCt0] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [twitterLogin, { loading }] = useMutation<TwitterLoginMutation, TwitterLoginMutationVariables>(TWITTER_LOGIN);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cookiesJson = JSON.stringify([
      { name: 'auth_token', value: authToken.trim() },
      { name: 'ct0', value: ct0.trim() },
    ]);

    const result = await twitterLogin({ variables: { username, cookiesJson } });
    const data = result.data?.twitterLogin;

    if (data?.success && data.sessionToken) {
      localStorage.setItem('session_token', data.sessionToken);
      navigate('/');
    } else {
      setError(data?.error ?? 'Login failed. Check your cookies and try again.');
    }
  }, [username, authToken, ct0, twitterLogin, navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div>
          <div className={styles.heading}>X Timeline</div>
          <div className={styles.subheading}>Connect your Twitter / X account</div>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="username">Twitter username</label>
            <input
              id="username"
              className={styles.input}
              type="text"
              placeholder="@handle"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="auth-token">auth_token</label>
            <input
              id="auth-token"
              className={styles.input}
              type="password"
              placeholder="Paste value from DevTools"
              value={authToken}
              onChange={e => setAuthToken(e.target.value)}
              autoComplete="off"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="ct0">ct0</label>
            <input
              id="ct0"
              className={styles.input}
              type="password"
              placeholder="Paste value from DevTools"
              value={ct0}
              onChange={e => setCt0(e.target.value)}
              autoComplete="off"
              required
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button className={styles.submit} type="submit" disabled={loading}>
            {loading ? 'Saving...' : 'Connect account'}
          </button>
        </form>

        <p className={styles.hint}>
          Open twitter.com → DevTools (F12) → Application → Cookies → twitter.com.
          Find <strong>auth_token</strong> and <strong>ct0</strong> and paste their values above.
          These are encrypted before being stored.
        </p>
      </div>
    </div>
  );
}
