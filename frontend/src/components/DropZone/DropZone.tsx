import { useRef, useState, useCallback, type DragEvent, type ChangeEvent } from 'react';
import styles from '@/styles/DropZone.module.css';

type ZoneState = 'idle' | 'drag-over' | 'accepted';

interface DropZoneProps {
  onFileAccepted: (file: File) => void;
  accept?: string;
}

export function DropZone({ onFileAccepted, accept = '.json,application/json' }: DropZoneProps) {
  const [state, setState] = useState<ZoneState>('idle');
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);

  const acceptFile = useCallback(
    (file: File) => {
      setFileName(file.name);
      setState('accepted');
      onFileAccepted(file);
    },
    [onFileAccepted],
  );

  const handleClick = () => inputRef.current?.click();

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) acceptFile(file);
    e.target.value = '';
  };

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounterRef.current += 1;
    if (state !== 'accepted') setState('drag-over');
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0 && state !== 'accepted') setState('idle');
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => e.preventDefault();

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    const file = e.dataTransfer.files?.[0];
    if (file) acceptFile(file);
  };

  const zoneClass = [
    styles.zone,
    state === 'drag-over' ? styles.dragOver : '',
    state === 'accepted' ? styles.accepted : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={zoneClass}
      onClick={handleClick}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && handleClick()}
      aria-label="Upload timeline JSON file"
    >
      <div className={styles.overlay} aria-hidden="true" />
      <div className={styles.plusBtn} aria-hidden="true">+</div>
      <div className={styles.textGroup}>
        <div className={styles.title}>UPLOAD TIMELINE JSON</div>
        {fileName ? (
          <div className={styles.filename}>{fileName}</div>
        ) : (
          <div className={styles.subtitle}>Drop file here or click to browse</div>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className={styles.hiddenInput}
        onChange={handleInputChange}
        tabIndex={-1}
        aria-hidden="true"
      />
    </div>
  );
}
