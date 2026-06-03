import type { DigestCluster } from '@/types';
import styles from '@/styles/TopicBlock.module.css';

interface TopicBlockProps {
  cluster: DigestCluster;
  index: number;
  maxImportance: number;
}

function volTier(importance: number, max: number): string {
  const ratio = importance / max;
  if (ratio >= 0.6) return 'HIGH';
  if (ratio >= 0.25) return 'MED';
  return 'LOW';
}

export function TopicBlock({ cluster, index, maxImportance }: TopicBlockProps) {
  const vol = volTier(cluster.total_importance, maxImportance);
  const indexLabel = String(index + 1).padStart(2, '0');

  return (
    <article className={styles.block}>
      <div className={styles.crosshair} aria-hidden="true" />
      <aside className={styles.meta}>
        <span className={styles.index}>{indexLabel}</span>
        <div className={styles.tags}>
          <span>SRC: {cluster.tweet_count} TWEETS</span>
          <span>VOL: {vol}</span>
        </div>
      </aside>
      <div className={styles.content}>
        <h2 className={styles.title}>{cluster.label}</h2>
        <p className={styles.summary}>{cluster.summary}</p>
        {cluster.bullets.length > 0 && (
          <ul className={styles.bullets}>
            {cluster.bullets.map((bullet, i) => (
              <li key={i} className={styles.bullet}>
                <span className={styles.bulletText}>{bullet.text}</span>
                {bullet.urls.length > 0 && (
                  <span className={styles.sources}>
                    {bullet.urls.map((url, j) => (
                      <a
                        key={j}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.sourceLink}
                      >
                        ↗
                      </a>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
