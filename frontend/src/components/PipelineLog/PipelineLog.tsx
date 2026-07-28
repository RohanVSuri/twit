import type { PipelineStep } from '@/types';
import styles from '@/styles/PipelineLog.module.css';

interface PipelineLogProps {
  steps: PipelineStep[];
}

function StepRow({ step, index, total }: { step: PipelineStep; index: number; total: number }) {
  const { status, name, elapsed } = step;

  const indicatorClass =
    status === 'complete' ? styles.indicatorDone
    : status === 'running' ? styles.indicatorRunning
    : styles.indicatorPending;

  const stepNumClass =
    status === 'complete' ? styles.stepNumDone
    : status === 'running' ? styles.stepNumRunning
    : styles.stepNumPending;

  const nameClass =
    status === 'complete' ? styles.nameDone
    : status === 'running' ? styles.nameRunning
    : styles.namePending;

  const indicator =
    status === 'complete' ? '[OK]'
    : status === 'running' ? '>>'
    : '[  ]';

  const timing =
    status === 'complete' && elapsed !== null ? `${elapsed}s`
    : status === 'running' ? <span className={styles.cursor} />
    : '--';

  return (
    <div className={styles.row}>
      <span className={`${styles.indicator} ${indicatorClass}`}>{indicator}</span>
      <span className={`${styles.stepNum} ${stepNumClass}`}>[{index + 1}/{total}]</span>
      <span className={`${styles.name} ${nameClass}`}>{name}</span>
      <span className={styles.timing}>{timing}</span>
    </div>
  );
}

export function PipelineLog({ steps }: PipelineLogProps) {
  return (
    <div className={styles.log}>
      {steps.map((step, i) => (
        <StepRow key={step.id} step={step} index={i} total={steps.length} />
      ))}
    </div>
  );
}
