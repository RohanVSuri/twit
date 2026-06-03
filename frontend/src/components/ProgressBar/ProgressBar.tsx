import styles from '@/styles/ProgressBar.module.css';

interface ProgressBarProps {
  progress: number;
  label?: string;
}

export function ProgressBar({ progress, label = 'Progress' }: ProgressBarProps) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.labels}>
        <span>{label}</span>
        <span className={styles.pct}>{progress}%</span>
      </div>
      <div className={styles.track}>
        <div className={styles.fill} style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
