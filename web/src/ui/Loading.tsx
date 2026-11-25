import { Icon } from "./Icon";
import "./Loading.css";

// No skeletons: a spinner and the same word the screens always showed. Under reduced motion the
// spinner stops and the word stays (styles/base.css).
export function Loading() {
  return (
    <span className="loading" role="status">
      <Icon name="spinner" />
      Loading…
    </span>
  );
}
