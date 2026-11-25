import type { Verdict } from "../api";
import { Icon, type IconName } from "./Icon";
import "./Badge.css";

const VERDICTS: Record<Verdict["verdict"], { label: string; icon: IconName; modifier: string }> = {
  met: { label: "Met", icon: "check-circle", modifier: "badge--met" },
  partial: { label: "Partial", icon: "partial", modifier: "badge--partial" },
  not_met: { label: "Not met", icon: "x-circle", modifier: "badge--not-met" },
};

// An icon and a word, so the verdict reads without colour.
export function VerdictBadge({ verdict }: { verdict: Verdict["verdict"] }) {
  const { label, icon, modifier } = VERDICTS[verdict];
  return (
    <span className={`badge ${modifier}`}>
      <Icon name={icon} />
      {label}
    </span>
  );
}
