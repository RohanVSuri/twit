import type { PipelineStatus } from '@/types';
import styles from '@/styles/StatusBadge.module.css';

const STATUS_LABELS: Record<PipelineStatus, string> = {
  ready: 'READY',
  'file-loaded': 'READY',
  processing: 'PROCESSING',
  complete: 'COMPLETE',
  error: 'ERROR',
};

const STATUS_STYLE: Record<PipelineStatus, string> = {
  ready: styles.ready,
  'file-loaded': styles.fileLo,
  processing: styles.processing,
  complete: styles.complete,
  error: styles.error,
};

interface StatusBadgeProps {
  status: PipelineStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`${styles.badge} ${STATUS_STYLE[status]}`}>
      STATUS: {STATUS_LABELS[status]}
    </span>
  );
}
