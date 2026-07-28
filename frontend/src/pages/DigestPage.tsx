import { useParams } from 'react-router';
import { useQuery } from '@apollo/client/react';
import { Canvas } from '@/components/Canvas';
import { NavBar } from '@/components/NavBar';
import { TopicBlock } from '@/components/TopicBlock';
import type { DigestCluster } from '@/types';
import type { DigestQuery, DigestQueryVariables } from '@/types/__generated__/graphql';
import { DIGEST } from '@/operations/timeline';
import styles from '@/styles/DigestPage.module.css';

export function DigestPage() {
  const { jobId = '' } = useParams<{ jobId: string }>();

  const { data, error } = useQuery<DigestQuery, DigestQueryVariables>(DIGEST, {
    variables: { jobId },
    skip: !jobId,
  });

  const clusters: DigestCluster[] = (data?.digest?.clusters ?? []).filter((c) => c.label.toLowerCase() !== 'miscellaneous').map((c) => ({
    id: c.id,
    label: c.label,
    summary: c.summary,
    bullets: c.bullets,
    tweet_count: c.tweetCount,
    total_importance: c.totalImportance,
  }));

  const maxImportance = clusters.length
    ? Math.max(...clusters.map((c) => c.total_importance))
    : 1;

  return (
    <Canvas>
      <NavBar status="complete" controls={<></>} />
      <main className={styles.feed}>
        {error && (
          <div style={{ padding: '2rem', color: 'var(--color-error, #f55)' }}>
            Failed to load digest: {error.message}
          </div>
        )}
        {clusters.map((cluster, i) => (
          <TopicBlock key={cluster.id} cluster={cluster} index={i} maxImportance={maxImportance} />
        ))}
        <div className={styles.eof}>END OF SYNTHESIS</div>
      </main>
    </Canvas>
  );
}
