import styles from '@/styles/NavButton.module.css';

interface NavButtonProps {
  label: string;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
}

export function NavButton({ label, onClick, active = false, disabled = false }: NavButtonProps) {
  const className = [styles.btn, active ? styles.active : '', disabled ? styles.disabled : '']
    .filter(Boolean)
    .join(' ');

  return (
    <button className={className} onClick={disabled ? undefined : onClick} aria-disabled={disabled}>
      {label}
    </button>
  );
}
