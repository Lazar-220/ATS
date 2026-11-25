import { Button } from "./Button";
import { Icon } from "./Icon";
import "./Notice.css";

// One shape for a failed request, so every screen offers the same retry. The message is shown as
// the API wrote it; it is text, never markup.
export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice" role="alert">
      <Icon name="alert-circle" />
      <span className="notice__msg">{message}</span>
      {onRetry && (
        <Button variant="secondary" size="sm" icon="refresh" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
