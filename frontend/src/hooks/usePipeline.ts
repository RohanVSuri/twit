import { useState, useCallback, useEffect } from 'react';
import { useMutation, useQuery } from '@apollo/client/react';
import type { PipelineStep } from '@/types';
import type { JobStatusQuery, JobStatusQueryVariables, RunPipelineMutation, RunPipelineMutationVariables } from '@/types/__generated__/graphql';
import { RUN_PIPELINE, JOB_STATUS } from '@/operations/timeline';

const STEP_MESSAGES: Record<string, string> = {
  score:     'SCORING TWEETS...',
  embed:     'EMBEDDING TWEETS...',
  cluster:   'CLUSTERING TOPICS...',
  summarize: 'GENERATING SUMMARIES...',
};

interface UsePipelineReturn {
  steps: PipelineStep[];
  progress: number;
  activeMessage: string;
  isDone: boolean;
  isError: boolean;
  start: (jobId: string) => void;
}

export function usePipeline(): UsePipelineReturn {
  const [jobId, setJobId] = useState<string | null>(null);
  const [isDone, setIsDone] = useState(false);
  const [isError, setIsError] = useState(false);
  const [activeMessage, setActiveMessage] = useState('');

  const [runPipeline] = useMutation<RunPipelineMutation, RunPipelineMutationVariables>(RUN_PIPELINE);

  const { data, stopPolling } = useQuery<JobStatusQuery, JobStatusQueryVariables>(JOB_STATUS, {
    variables: { jobId: jobId! },
    skip: !jobId,
    pollInterval: 5000,
  });

  const status = data?.jobStatus;

  useEffect(() => {
    if (!status) return;

    const running = status.steps?.find((s) => s.status === 'running');
    if (running) setActiveMessage(STEP_MESSAGES[running.id] ?? running.name);

    if (status.status === 'complete') {
      setActiveMessage('PIPELINE COMPLETE');
      setIsDone(true);
      stopPolling();
    } else if (status.status === 'error') {
      setActiveMessage(`ERROR: ${status.error ?? 'unknown'}`);
      setIsError(true);
      stopPolling();
    }
  }, [status, stopPolling]);

  const start = useCallback((id: string) => {
    setJobId(id);
    runPipeline({ variables: { jobId: id } }).catch(console.error);
  }, [runPipeline]);

  return {
    steps: (status?.steps ?? []).map((s) => ({ ...s, status: s.status as PipelineStep['status'], elapsed: s.elapsed ?? null })),
    progress: status?.progress ?? 0,
    activeMessage,
    isDone,
    isError,
    start,
  };
}
