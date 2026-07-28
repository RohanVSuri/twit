import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';
import { useMutation } from '@apollo/client/react';
import type { PipelineStatus } from '@/types';
import type { TwitterLogoutMutation } from '@/types/__generated__/graphql';
import { NavButton } from '@/components/NavButton';
import { StatusBadge } from '@/components/StatusBadge';
import { TWITTER_LOGOUT } from '@/operations/timeline';
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
  const navigate = useNavigate();
  const [twitterLogout] = useMutation<TwitterLogoutMutation>(TWITTER_LOGOUT);

  const handleLogout = async () => {
    try {
      await twitterLogout();
    } finally {
      localStorage.removeItem('session_token');
      navigate('/login');
    }
  };

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
      <Link to="/" className={styles.brand}>FEED SYNTH</Link>
      <div className={styles.controls}>
        {controls ?? defaultControls}
        <StatusBadge status={status} />
        <NavButton label="LOGOUT" onClick={handleLogout} />
      </div>
    </header>
  );
}
