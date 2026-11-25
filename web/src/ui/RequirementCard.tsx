import type { Verdict } from "../api";
import { verdictFlagText } from "../flags";
import { quoteState } from "../highlight";
import { FlagNote } from "./FlagNote";
import { QuoteState } from "./QuoteState";
import { VerdictBadge } from "./VerdictBadge";
import "./RequirementCard.css";

type RequirementCardProps = {
  // The row's number in the requirements editor, for the same version of the rubric.
  number: number;
  verdict: Verdict;
  selected: boolean;
  onSelect: () => void;
};

// The title is the button, and its ::after stretches it over the whole card; the flags sit above
// that layer. So the card is one click target without the button's name being the entire card.
export function RequirementCard({ number, verdict, selected, onSelect }: RequirementCardProps) {
  const quote = quoteState(verdict);
  return (
    <li className={verdict.parent_id === null ? "req" : "req req--child"}>
      <div className="req__top">
        <span className="req__no">{number}</span>
        <button type="button" className="req__select" aria-pressed={selected} onClick={onSelect}>
          {verdict.text}
        </button>
      </div>
      <div className="req__body">
        <div className="req__meta">
          {verdict.kind === "mandatory" ? "mandatory" : "nice to have"}, weight {verdict.weight}
          {verdict.min_months !== null && `, minimum ${verdict.min_months} months`}
        </div>
        <div className="req__verdict">
          Verdict: <VerdictBadge verdict={verdict.verdict} />
        </div>
        {verdict.rationale && <p className="req__rationale">{verdict.rationale}</p>}
        {quote !== "none" && <QuoteState verified={quote === "verified"} />}
        {verdict.flags.map((flag) => (
          <FlagNote key={flag.code} compact {...verdictFlagText(flag)} />
        ))}
      </div>
    </li>
  );
}
