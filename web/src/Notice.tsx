// One shape for a failed request, so every screen offers the same retry.
export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <p role="alert" style={{ color: "var(--color-error)" }}>
      {message}{" "}
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </p>
  );
}
