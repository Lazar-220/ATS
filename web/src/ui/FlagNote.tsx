import type { FlagText } from "../flags";
import { Icon } from "./Icon";
import "./FlagNote.css";

// A thing HR should know about a CV or a verdict. The body may quote the CV, so it is text only.
export function FlagNote({ title, code, body, compact = false }: FlagText & { compact?: boolean }) {
  return (
    <div className={compact ? "flag flag--compact" : "flag"} role="note">
      <Icon name="alert-triangle" />
      <div className="flag__head">
        <span className="flag__title">{title}</span>
        {code !== null && <span className="flag__code">{code}</span>}
      </div>
      {body !== null && <div className="flag__body">{body}</div>}
    </div>
  );
}
