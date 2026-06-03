import type { ReactNode } from 'react';
import type { PipelineStatus } from '@/types';
import { NavButton } from '@/components/NavButton';
import { StatusBadge } from '@/components/StatusBadge';
import styles from '@/styles/NavBar.module.css';

interface NavBarProps {
  status: PipelineStatus;
  controls?: ReactNode;
  onUploadClick?: () => void;
  onRunClick?: () => void;
  activeControl?: 'upload' | 'run';
  runDisabled?: boolean;
}

export function NavBar({
  status,
  controls,
  onUploadClick,
  onRunClick,
  activeControl,
  runDisabled = false,
}: NavBarProps) {
  const defaultControls = (
    <>
      <NavButton
        label="UPLOAD JSON"
        onClick={onUploadClick}
        active={activeControl === 'upload'}
      />
      <NavButton
        label="RUN PIPELINE"
        onClick={onRunClick}
        active={activeControl === 'run'}
        disabled={runDisabled}
      />
    </>
  );

  return (
    <header className={styles.header}>
      <div className={styles.brand}>FEED SYNTH</div>
      <div className={styles.controls}>
        {controls ?? defaultControls}
        <StatusBadge status={status} />
      </div>
    </header>
  );
}
