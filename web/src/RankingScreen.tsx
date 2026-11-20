import { usePosition, usePositionRanking } from "./hooks";
import { RankingTable } from "./RankingTable";

export function RankingScreen({
  positionId,
  onOpenAssessment,
}: {
  positionId: string;
  onOpenAssessment: (assessmentId: string) => void;
}) {
  const position = usePosition(positionId);
  // Rows appear as the worker finishes each CV, so the list is refreshed while it is open.
  const ranking = usePositionRanking(positionId, true);

  return (
    <section>
      <h2>Ranked list{position.data?.filename ? `: ${position.data.filename}` : ""}</h2>
      {ranking.isPending && <p>Loading…</p>}
      {ranking.isError && <p role="alert">{ranking.error.message}</p>}
      {ranking.data && ranking.data.rows.length === 0 && (
        <p>
          No CV has been assessed yet. Results appear here as the worker finishes each CV; if you
          just uploaded, give it a moment.
        </p>
      )}
      {ranking.data && ranking.data.rows.length > 0 && (
        <>
          {ranking.data.rubric_status === "unconfirmed" && (
            <p>
              The requirements are not confirmed yet, so these scores are provisional. Confirm or
              edit them on the requirements screen.
            </p>
          )}
          <RankingTable rows={ranking.data.rows} onOpen={onOpenAssessment} />
        </>
      )}
    </section>
  );
}
