import { href } from "./route";
import { usePosition, usePositionRanking } from "./hooks";
import { ProvisionalBanner } from "./ui/Banner";
import { EmptyState } from "./ui/EmptyState";
import { Link } from "./ui/Link";
import { Loading } from "./ui/Loading";
import { ErrorNotice } from "./ui/Notice";
import { Popover } from "./ui/Popover";
import { RankingTable } from "./RankingTable";
import "./RankingScreen.css";

// The board's explanation of what src/ats/pipeline/score.py computes; change both together.
const SCORE_HELP =
  "Met counts 1, Partial 0.5, Not met 0. Within each kind, requirements are weighted by their weight (1–5). Mandatory requirements make 70% of the score and nice-to-have 30%; if a posting has only one kind, that kind is the whole score. A requirement and its refinements count once, with the requirement's weight and kind, as the average of their verdicts. Only Not met fails a mandatory requirement.";

export function RankingScreen({ positionId }: { positionId: string }) {
  const position = usePosition(positionId);
  // Rows appear as the worker finishes each CV, so the list is refreshed while it is open.
  const ranking = usePositionRanking(positionId, true);

  return (
    <div className="ranking-screen">
      <div className="page-head">
        <h1 className="h1">Ranked list{position.data?.filename ? `: ${position.data.filename}` : ""}</h1>
        <div className="ranking-actions">
          <Popover title="How the score works">{SCORE_HELP}</Popover>
          <Link href={href({ name: "requirements", positionId })}>Requirements</Link>
        </div>
      </div>
      {ranking.isPending && (
        <div>
          <Loading />
        </div>
      )}
      {ranking.isError && (
        <ErrorNotice message={ranking.error.message} onRetry={() => void ranking.refetch()} />
      )}
      {ranking.data && ranking.data.rows.length === 0 && (
        <EmptyState>
          No CV has been assessed yet. Results appear here as the worker finishes each CV; if you
          just uploaded, give it a moment.
        </EmptyState>
      )}
      {ranking.data && ranking.data.rows.length > 0 && (
        <>
          {ranking.data.rubric_status === "unconfirmed" && (
            <ProvisionalBanner>
              The requirements are not confirmed yet, so these scores are provisional. Confirm or
              edit them on the requirements screen.
            </ProvisionalBanner>
          )}
          <RankingTable rows={ranking.data.rows} positionId={positionId} />
        </>
      )}
    </div>
  );
}
