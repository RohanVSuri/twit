import type { ReactNode } from 'react';
import styles from '@/styles/Canvas.module.css';

interface CanvasProps {
  children: ReactNode;
}

export function Canvas({ children }: CanvasProps) {
  return <div className={styles.canvas}>{children}</div>;
}
