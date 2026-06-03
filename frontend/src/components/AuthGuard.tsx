import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { useQuery } from '@apollo/client/react';
import type { MeQuery } from '@/types/__generated__/graphql';
import { ME } from '@/operations/timeline';

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const navigate = useNavigate();
  const { data, loading, error } = useQuery<MeQuery>(ME, {
    fetchPolicy: 'network-only',
  });

  if (loading) return null;

  if (error || !data?.me) {
    if (error) localStorage.removeItem('session_token');
    navigate('/login');
    return null;
  }

  return <>{children}</>;
}
