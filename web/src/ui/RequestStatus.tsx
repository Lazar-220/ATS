import type { RankingStatus } from "../api";
import { requestLabel } from "../status";
import { Icon, type IconName } from "./Icon";
import "./RequestStatus.css";

type Status = RankingStatus["status"];

// The board calls the looks waiting and processing; the component takes the API status.
const LOOK: Record<Status, { className: string; icon: IconName }> = {
  queued: { className: "req-status--waiting", icon: "clock" },
  running: { className: "req-status--processing", icon: "spinner" },
  done: { className: "req-status--done", icon: "check-circle" },
  failed: { className: "req-status--failed", icon: "x-circle" },
};

export function RequestStatus({ status }: { status: Status }) {
  const look = LOOK[status];
  return (
    <div className={`req-status ${look.className}`} role="status" aria-live="polite" data-testid="request-status">
      <span className="req-status__label">Status: </span>
      <span className="req-status__value">
        <Icon name={look.icon} />
        <span>{requestLabel(status)}</span>
      </span>
    </div>
  );
}
