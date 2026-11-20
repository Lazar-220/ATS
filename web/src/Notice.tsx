// One shape for a failed request, so every screen offers the same retry.
export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <p role="alert" style={{ color: "#b00020" }}>
      {message}{" "}
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </p>
  );
}
