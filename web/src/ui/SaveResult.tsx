import { Icon } from "./Icon";
import { ErrorNotice } from "./Notice";

type SaveResultProps = { kind: "saved" | "already" } | { kind: "error"; message: string };

// What came of Save or Confirm. An API message is shown as it was written.
export function SaveResult(props: SaveResultProps) {
  if (props.kind === "error") {
    return <ErrorNotice message={props.message} />;
  }
  const saved = props.kind === "saved";
  return (
    <div className={saved ? "notice notice--success" : "notice notice--info"} role="status">
      <Icon name={saved ? "check" : "info"} />
      <span className="notice__msg">{saved ? "Saved." : "Already saved."}</span>
    </div>
  );
}
