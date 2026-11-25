import { useMemo, useState } from "react";

import type { Assessment } from "./api";
import { cvFlagText } from "./flags";
import { useAssessment } from "./hooks";
import { formatScore } from "./ranking";
import { ProvisionalBanner } from "./ui/Banner";
import { CvViewer } from "./ui/CvViewer";
import { FlagNote } from "./ui/FlagNote";
import { Loading } from "./ui/Loading";
import { ErrorNotice } from "./ui/Notice";
import { RequirementCard } from "./ui/RequirementCard";
import "./AssessmentScreen.css";

function Summary({ assessment }: { assessment: Assessment }) {
  return (
    <div className="assessment__head">
      <h1 className="h1">
        {assessment.candidate_name ?? <span className="name-missing">(name not found)</span>}
      </h1>
      <p className="summary">
        {assessment.filename} · score <strong>{formatScore(assessment)}</strong>
        {assessment.mandatory_failed && " · a mandatory requirement is not met"}
        {assessment.tenure && ` · ${String(assessment.tenure["total_months"] ?? "?")} months of experience`}
      </p>
    </div>
  );
}

function AssessmentView({ assessment }: { assessment: Assessment }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const quotes = useMemo(
    () =>
      assessment.verdicts.flatMap((v) =>
        v.evidence === null
          ? []
          : [{ id: v.requirement_id, char_start: v.evidence.char_start, char_end: v.evidence.char_end }],
      ),
    [assessment.verdicts],
  );

  return (
    <div className="assessment">
      <Summary assessment={assessment} />
      {assessment.rubric_unconfirmed && <ProvisionalBanner>rubric unconfirmed</ProvisionalBanner>}
      {assessment.status === "failed" && (
        <ErrorNotice
          message={`This CV could not be assessed${assessment.error ? `: ${assessment.error}` : "."}`}
        />
      )}
      {assessment.cv_flags.length > 0 && (
        <div className="flags">
          {assessment.cv_flags.map((flag) => (
            <FlagNote key={flag.code} {...cvFlagText(flag.code)} />
          ))}
        </div>
      )}
      <div className="assess">
        <section className="pane" aria-label="Requirements and verdicts">
          {assessment.verdicts.length === 0 ? (
            <p className="pane-empty">This assessment has no verdicts.</p>
          ) : (
            // The API lists the verdicts in the rubric's order, so the numbers count along it.
            <ul className="cards">
              {assessment.verdicts.map((verdict, index) => (
                <RequirementCard
                  key={verdict.requirement_id}
                  number={index + 1}
                  verdict={verdict}
                  selected={selectedId === verdict.requirement_id}
                  onSelect={() => setSelectedId(verdict.requirement_id)}
                />
              ))}
            </ul>
          )}
        </section>
        <section aria-label="CV text">
          {assessment.cv_text === null ? (
            <p className="pane-empty">The CV text is not available.</p>
          ) : (
            <CvViewer text={assessment.cv_text} quotes={quotes} selectedId={selectedId} />
          )}
        </section>
      </div>
    </div>
  );
}

export function AssessmentScreen({ assessmentId }: { assessmentId: string }) {
  const assessment = useAssessment(assessmentId);

  if (assessment.isPending) {
    return (
      <div>
        <Loading />
      </div>
    );
  }
  if (assessment.isError) {
    return (
      <ErrorNotice message={assessment.error.message} onRetry={() => void assessment.refetch()} />
    );
  }
  // Keyed, because two assessments of one position share requirement ids: a selection must not
  // carry over from one CV to another.
  return <AssessmentView key={assessment.data.assessment_id} assessment={assessment.data} />;
}
