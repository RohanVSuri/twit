import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useMutation, useQuery } from '@apollo/client/react';
import { Canvas } from '@/components/Canvas';
import { NavBar } from '@/components/NavBar';
import { DropZone } from '@/components/DropZone';
import type { PipelineStatus } from '@/types';
import type {
  MeQuery,
  UploadTimelineMutation, UploadTimelineMutationVariables,
  FetchTimelineMutation,
} from '@/types/__generated__/graphql';
import { ME, UPLOAD_TIMELINE, FETCH_TIMELINE } from '@/operations/timeline';
import styles from '@/styles/UploadPage.module.css';

export function UploadPage() {
  const navigate = useNavigate();
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [status, setStatus] = useState<PipelineStatus>('ready');
  const [fetchError, setFetchError] = useState<string | null>(null);

  const { data: meData } = useQuery<MeQuery>(ME);
  const latestJobId = meData?.me?.latestJobId;

  const [uploadTimeline, { loading: uploading }] = useMutation<UploadTimelineMutation, UploadTimelineMutationVariables>(UPLOAD_TIMELINE);
  const [fetchTimeline, { loading: fetching }] = useMutation<FetchTimelineMutation>(FETCH_TIMELINE);

  const handleFileAccepted = useCallback((file: File) => {
    setUploadedFile(file);
    setStatus('file-loaded');
  }, []);

  const handleRun = useCallback(async () => {
    if (!uploadedFile) return;
    setStatus('processing');
    const result = await uploadTimeline({ variables: { file: uploadedFile } });
    const jobId = result.data?.uploadTimeline?.jobId;
    navigate('/pipeline', { state: { jobId } });
  }, [uploadedFile, uploadTimeline, navigate]);

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

  const fetchDisabled = fetching || uploading || !!uploadedFile;

  return (
    <Canvas>
      <NavBar status={status} controls={<></>} />
      <main className={styles.main}>
        <div className={styles.fetchSection}>
          <button
            className={styles.fetchButton}
            onClick={handleFetchTimeline}
            disabled={fetchDisabled}
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
          <p className={styles.fetchDivider}>— or drop a saved timeline —</p>
        </div>
        <DropZone onFileAccepted={handleFileAccepted} />
        {uploadedFile && (
          <button
            className={styles.runButton}
            onClick={handleRun}
            disabled={uploading}
          >
            {uploading ? 'LOADING...' : `RUN  ↑  ${uploadedFile.name}`}
          </button>
        )}
      </main>
    </Canvas>
  );
}
