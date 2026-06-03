import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { Canvas } from '@/components/Canvas';
import { NavBar } from '@/components/NavBar';
import { ProgressBar } from '@/components/ProgressBar';
import { PipelineLog } from '@/components/PipelineLog';
import { usePipeline } from '@/hooks/usePipeline';
import styles from '@/styles/PipelinePage.module.css';

export function PipelinePage() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const jobId: string = state?.jobId ?? '';
  const { steps, progress, activeMessage, isDone, isError, start } = usePipeline();

  useEffect(() => {
    if (jobId) start(jobId);
  }, [jobId, start]);

  useEffect(() => {
    if (isDone) {
      const t = setTimeout(() => navigate(`/digest/${jobId}`), 800);
      return () => clearTimeout(t);
    }
  }, [isDone, navigate, jobId]);

  const navStatus = isError ? 'error' : isDone ? 'complete' : 'processing';

  return (
    <Canvas>
      <NavBar status={navStatus} activeControl="run" />
      <main className={styles.main}>
        <div className={styles.content}>
          <div className={styles.header}>
            <div className={styles.activeMessage}>{'>>'} {activeMessage}</div>
          </div>
          <ProgressBar progress={progress} />
          <PipelineLog steps={steps} />
        </div>
      </main>
    </Canvas>
  );
}
