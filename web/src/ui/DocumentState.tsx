import { documentLabel, documentNeedsAttention } from "../status";
import { Icon, type IconName } from "./Icon";
import "./DocumentState.css";

// An unknown state gets the info icon and is shown raw (documentLabel).
const ICON: Record<string, IconName> = {
  uploaded: "clock",
  extracted: "file",
  parsed: "check",
  rejected: "alert-circle",
  failed: "alert-circle",
};

export function DocumentState({ status }: { status: string }) {
  const classes = ["state", status === "parsed" ? "state--ok" : "", documentNeedsAttention(status) ? "state--attention" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes}>
      <Icon name={ICON[status] ?? "info"} />
      <span>{documentLabel(status)}</span>
    </span>
  );
}
