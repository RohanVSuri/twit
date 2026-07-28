import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useMutation, useQuery } from '@apollo/client/react';
import { Canvas } from '@/components/Canvas';
import { NavBar } from '@/components/NavBar';
import type { PipelineStatus } from '@/types';
import type { MeQuery, FetchTimelineMutation } from '@/types/__generated__/graphql';
import { ME, FETCH_TIMELINE } from '@/operations/timeline';
import styles from '@/styles/UploadPage.module.css';

export function UploadPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<PipelineStatus>('ready');
  const [fetchError, setFetchError] = useState<string | null>(null);

  const { data: meData } = useQuery<MeQuery>(ME);
  const latestJobId = meData?.me?.latestJobId;

  const [fetchTimeline, { loading: fetching }] = useMutation<FetchTimelineMutation>(FETCH_TIMELINE);

  const handleFetchTimeline = useCallback(async () => {
    setFetchError(null);
    setStatus('processing');
    try {
      const result = await fetchTimeline();
      const jobId = result.data?.fetchTimeline?.jobId;
      navigate('/pipeline', { state: { jobId } });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes('Not authenticated') || msg.includes('log in')) {
        navigate('/login');
      } else {
        setFetchError(msg);
        setStatus('ready');
      }
    }
  }, [fetchTimeline, navigate]);

  return (
    <Canvas>
      <NavBar status={status} controls={<></>} />
      <main className={styles.main}>
        <div className={styles.fetchSection}>
          <button
            className={styles.fetchButton}
            onClick={handleFetchTimeline}
            disabled={fetching}
          >
            {fetching ? 'FETCHING...' : 'FETCH MY TIMELINE'}
          </button>
          {latestJobId && (
            <button
              className={styles.latestLink}
              onClick={() => navigate(`/digest/${latestJobId}`)}
            >
              view latest digest →
            </button>
          )}
          {fetchError && <p className={styles.fetchError}>{fetchError}</p>}
        </div>
      </main>
    </Canvas>
  );
}
