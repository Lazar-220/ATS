import { useEffect, useId, useState, type ReactNode } from "react";

import "./Tooltip.css";

type TooltipProps = {
  // Null: there is nothing to say, so there is no tooltip.
  content: string | null;
  // The focusable trigger. It receives the id for its aria-describedby.
  children: (describedBy: string | undefined) => ReactNode;
};

// Shows while the trigger or the tooltip is hovered or focused (the CSS does that), and Esc hides
// it until the next hover or focus (WCAG 1.4.13). The wrapper stays when the content goes, so
// the trigger is never re-created under the user's focus.
export function Tooltip({ content, children }: TooltipProps) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  const present = content !== null;

  // On the document, because Esc must also work when only the pointer is on the tooltip.
  useEffect(() => {
    if (!present) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDismissed(true);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [present]);

  return (
    <span
      className="tip-wrap"
      data-dismissed={dismissed || undefined}
      onPointerEnter={() => setDismissed(false)}
      onFocus={() => setDismissed(false)}
    >
      {present && (
        <span className="tooltip" role="tooltip" id={id}>
          {content}
        </span>
      )}
      {children(present ? id : undefined)}
    </span>
  );
}
