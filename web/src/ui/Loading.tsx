import { Icon } from "./Icon";
import "./Loading.css";

// No skeletons: a spinner and a word that says what is awaited. Under reduced motion the
// spinner stops and the word stays (styles/base.css).
export function Loading({ children = "Loading…" }: { children?: string }) {
  return (
    <span className="loading" role="status">
      <Icon name="spinner" />
      {children}
    </span>
  );
}
