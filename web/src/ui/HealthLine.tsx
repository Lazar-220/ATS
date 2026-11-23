import type { Health } from "../api";
import type { HealthState } from "../health";
import "./HealthLine.css";
import { Icon, type IconName } from "./Icon";

export type HealthLineProps = {
  state: HealthState;
  api?: Health["status"];
  database?: Health["database"];
  message?: string;
};

const ICON: Record<HealthState, IconName> = {
  checking: "spinner",
  ok: "check-circle",
  degraded: "alert-triangle",
  unreachable: "x-circle",
};

// The icon follows the worst part: a degraded answer with the database down is drawn as a failure,
// as on the design board. The texts are the ones the app has always shown.
export function HealthLine({ state, api, database, message }: HealthLineProps) {
  const tone = state === "degraded" && database === "unreachable" ? "unreachable" : state;
  const icon = tone === "unreachable" ? "x-circle" : ICON[state];
  return (
    <span className={`health health--${tone}`} role="status">
      <Icon name={icon} />
      {state === "checking" && <span>Checking the API…</span>}
      {state === "unreachable" && <span data-testid="health">API unreachable: {message}</span>}
      {(state === "ok" || state === "degraded") && (
        <span data-testid="health">
          API: <strong>{api}</strong>, database: <strong>{database}</strong>
        </span>
      )}
    </span>
  );
}
