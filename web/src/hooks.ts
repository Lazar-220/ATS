import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchAssessment,
  fetchPosition,
  fetchPositionRanking,
  fetchPositions,
  fetchRankingStatus,
  uploadRanking,
} from "./api";
import { isSettled } from "./status";

const POLL_MS = 2000;

export function usePositions() {
  return useQuery({ queryKey: ["positions"], queryFn: fetchPositions, refetchInterval: 5000 });
}

export function usePosition(id: string) {
  return useQuery({ queryKey: ["position", id], queryFn: () => fetchPosition(id) });
}

// Polls until the request is done or failed, then stops: a settled request never changes.
export function useRankingStatus(requestId: string | null) {
  return useQuery({
    queryKey: ["ranking-status", requestId],
    queryFn: () => fetchRankingStatus(requestId ?? ""),
    enabled: requestId !== null,
    refetchInterval: (query) => (query.state.data && isSettled(query.state.data.status) ? false : POLL_MS),
  });
}

// The ranking moves while CVs are judged, so it is polled while its position still has work.
export function usePositionRanking(positionId: string, poll: boolean) {
  return useQuery({
    queryKey: ["position-ranking", positionId],
    queryFn: () => fetchPositionRanking(positionId),
    refetchInterval: poll ? POLL_MS : false,
  });
}

export function useAssessment(assessmentId: string) {
  return useQuery({
    queryKey: ["assessment", assessmentId],
    queryFn: () => fetchAssessment(assessmentId),
  });
}

export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ posting, cvs }: { posting: File; cvs: File[] }) => uploadRanking(posting, cvs),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["positions"] }),
  });
}
