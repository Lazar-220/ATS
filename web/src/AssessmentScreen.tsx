import { useEffect, useMemo, useRef, useState } from "react";

import type { Assessment, Verdict } from "./api";
import { quoteState, segment, toRanges } from "./highlight";
import { useAssessment } from "./hooks";
import { ErrorNotice } from "./Notice";
import { formatScore } from "./ranking";

const VERDICT_LABEL: Record<Verdict["verdict"], string> = {
  met: "Met",
  partial: "Partial",
  not_met: "Not met",
};

const FLAG_LABEL: Record<string, string> = {
  low_coverage: "Parts of this CV could not be read into structured data, so the facts may be incomplete.",
  suspected_injection: "This CV contains text that looks aimed at an automated screener. Read it with care.",
  hidden_text: "Hidden text (white, tiny, off-page or covered) was found in the PDF and left out of the assessment.",
  invisible_characters: "Invisible characters were found in the CV text and removed before the assessment.",
  mixed_script_words: "Some words mix Cyrillic and Latin letters, which can be an attempt to disguise text.",
};

function QuoteBadge({ verdict }: { verdict: Verdict }) {
  const state = quoteState(verdict);
  if (state === "verified") {
    return <span>quote found in the CV</span>;
  }
  if (state === "unverified") {
    return (
      <strong style={{ color: "var(--color-error)" }} data-testid="unverified">
        Unverified: the quote could not be found in the CV, so nothing is highlighted
      </strong>
    );
  }
  return null;
}

function RequirementItem({
  verdict,
  selected,
  onSelect,
}: {
  verdict: Verdict;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li
      style={{
        marginLeft: verdict.parent_id === null ? 0 : "1.5rem",
        marginBottom: "0.5rem",
        listStyle: "none",
      }}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        style={{
          textAlign: "left",
          width: "100%",
          padding: "0.5rem",
          border: selected ? "2px solid var(--color-accent)" : "1px solid var(--color-border-control)",
          background: selected ? "var(--color-accent-subtle-bg)" : "var(--color-bg-surface)",
          color: "var(--color-text-primary)",
          cursor: "pointer",
        }}
      >
        <div>
          <strong>{verdict.text}</strong>{" "}
          <small>
            {verdict.kind === "mandatory" ? "mandatory" : "nice to have"}, weight {verdict.weight}
            {verdict.min_months !== null && `, minimum ${verdict.min_months} months`}
          </small>
        </div>
        <div>
          Verdict: <strong>{VERDICT_LABEL[verdict.verdict]}</strong>
        </div>
        {verdict.rationale && <div>{verdict.rationale}</div>}
        <QuoteBadge verdict={verdict} />
        {verdict.flags.map((flag) => (
          <div key={flag.code} style={{ color: "var(--color-caution)" }}>
            Flag {flag.code}
            {flag.detail !== "" && `: ${flag.detail}`}
          </div>
        ))}
      </button>
    </li>
  );
}

function CvText({
  text,
  verdicts,
  selectedId,
}: {
  text: string;
  verdicts: Verdict[];
  selectedId: string | null;
}) {
  const segments = useMemo(() => {
    const evidence = verdicts.flatMap((v) =>
      v.evidence === null
        ? []
        : [{ id: v.requirement_id, char_start: v.evidence.char_start, char_end: v.evidence.char_end }],
    );
    return segment(text, toRanges(text, evidence));
  }, [text, verdicts]);
  const firstSelected = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // The pane scrolls, not the page, so the quote is centred inside it.
    firstSelected.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selectedId]);

  const firstIndex = segments.findIndex((part) => selectedId !== null && part.ids.includes(selectedId));
  return (
    <pre
      data-testid="cv-text"
      style={{
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        fontFamily: "inherit",
        margin: 0,
        maxHeight: "70vh",
        overflowY: "auto",
        border: "1px solid #ccc",
        padding: "0.75rem",
      }}
    >
      {segments.map((part, index) => {
        if (part.ids.length === 0) {
          return part.text;
        }
        const isSelected = selectedId !== null && part.ids.includes(selectedId);
        return (
          <mark
            key={index}
            ref={index === firstIndex ? firstSelected : undefined}
            style={{
              background: isSelected ? "var(--color-highlight-selected-bg)" : "var(--color-highlight-quote-bg)",
              color: "var(--color-text-primary)",
              outline: isSelected ? "2px solid var(--color-highlight-selected-outline)" : "none",
            }}
          >
            {part.text}
          </mark>
        );
      })}
    </pre>
  );
}

function Summary({ assessment }: { assessment: Assessment }) {
  return (
    <section>
      <h2>{assessment.candidate_name ?? "(name not found)"}</h2>
      <p>
        {assessment.filename} · score <strong>{formatScore(assessment)}</strong>
        {assessment.mandatory_failed && " · a mandatory requirement is not met"}
        {assessment.rubric_unconfirmed && " · rubric unconfirmed"}
        {assessment.tenure && ` · ${String(assessment.tenure["total_months"] ?? "?")} months of experience`}
      </p>
      {assessment.status === "failed" && (
        <p role="alert">This CV could not be assessed{assessment.error ? `: ${assessment.error}` : "."}</p>
      )}
      {assessment.cv_flags.map((flag) => (
        <p key={flag.code} role="note" style={{ color: "var(--color-caution)" }}>
          {FLAG_LABEL[flag.code] ?? flag.code}
        </p>
      ))}
    </section>
  );
}

export function AssessmentScreen({ assessmentId }: { assessmentId: string }) {
  const assessment = useAssessment(assessmentId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (assessment.isPending) {
    return <p>Loading…</p>;
  }
  if (assessment.isError) {
    return (
      <ErrorNotice message={assessment.error.message} onRetry={() => void assessment.refetch()} />
    );
  }
  const data = assessment.data;
  return (
    <div>
      <Summary assessment={data} />
      {data.verdicts.length === 0 && <p>This assessment has no verdicts.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: "1rem" }}>
        <ul style={{ padding: 0, margin: 0 }}>
          {data.verdicts.map((verdict) => (
            <RequirementItem
              key={verdict.requirement_id}
              verdict={verdict}
              selected={selectedId === verdict.requirement_id}
              onSelect={() => setSelectedId(verdict.requirement_id)}
            />
          ))}
        </ul>
        {data.cv_text === null ? (
          <p>The CV text is not available.</p>
        ) : (
          <CvText text={data.cv_text} verdicts={data.verdicts} selectedId={selectedId} />
        )}
      </div>
    </div>
  );
}
