import { href } from "./route";
import { usePosition, usePositionRanking } from "./hooks";
import { ErrorNotice } from "./ui/Notice";
import { Loading } from "./ui/Loading";
import { RankingTable } from "./RankingTable";

export function RankingScreen({ positionId }: { positionId: string }) {
  const position = usePosition(positionId);
  // Rows appear as the worker finishes each CV, so the list is refreshed while it is open.
  const ranking = usePositionRanking(positionId, true);

  return (
    <section>
      <p>
        <a href={href({ name: "requirements", positionId })}>Requirements</a>
      </p>
      <h2>Ranked list{position.data?.filename ? `: ${position.data.filename}` : ""}</h2>
      {ranking.isPending && <Loading />}
      {ranking.isError && (
        <ErrorNotice message={ranking.error.message} onRetry={() => void ranking.refetch()} />
      )}
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
          <RankingTable rows={ranking.data.rows} positionId={positionId} />
        </>
      )}
    </section>
  );
}
