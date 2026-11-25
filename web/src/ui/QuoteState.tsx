import { Icon } from "./Icon";
import "./QuoteState.css";

// Whether code found the judge's quote in the CV. A verdict that needs no quote has no such line.
export function QuoteState({ verified }: { verified: boolean }) {
  if (verified) {
    return (
      <span className="quote-state">
        <Icon name="quote" />
        <span>quote found in the CV</span>
      </span>
    );
  }
  return (
    <span className="quote-state quote-state--unverified" data-testid="unverified">
      <Icon name="alert-triangle" />
      <span>Unverified: the quote could not be found in the CV, so nothing is highlighted</span>
    </span>
  );
}
