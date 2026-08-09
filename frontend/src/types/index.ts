export type PipelineStatus = 'ready' | 'file-loaded' | 'processing' | 'complete' | 'error';

export interface PipelineStep {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  elapsed: number | null;
}

export interface DigestBulletSource {
  url: string;
  text: string;
  authorName: string;
  authorHandle: string;
}

export interface DigestBullet {
  text: string;
  urls: string[];
  sources: DigestBulletSource[];
}

export interface DigestCluster {
  id: number;
  label: string;
  summary: string;
  bullets: DigestBullet[];
  tweet_count: number;
  total_importance: number;
}
