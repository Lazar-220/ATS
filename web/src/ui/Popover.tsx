import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Button } from "./Button";
import "./Popover.css";

// A button that opens a small non-modal dialog under the same title. Esc, a click outside and
// the × close it, and the focus goes back to the button. The dialog is placed against the nearest
// positioned ancestor, so the caller decides which edge it lines up with.
export function Popover({ title, children }: { title: string; children: ReactNode }) {
  const dialogId = useId();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    // The button may have scrolled out of view; returning the focus must not move the page.
    trigger.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
      }
    }
    function onMouseDown(event: MouseEvent) {
      if (event.target instanceof Node && !anchor.current?.contains(event.target)) {
        // Without this the browser would then move the focus to whatever was pressed. The click
        // itself still happens.
        event.preventDefault();
        close();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, close]);

  return (
    <span className="pop-anchor" ref={anchor}>
      <Button
        ref={trigger}
        variant="ghost"
        icon="help-circle"
        aria-expanded={open}
        aria-controls={open ? dialogId : undefined}
        onClick={() => setOpen((current) => !current)}
      >
        {title}
      </Button>
      {open && (
        <div className="popover" id={dialogId} role="dialog" aria-labelledby={titleId}>
          <div className="popover__head">
            <h2 className="popover__title" id={titleId}>
              {title}
            </h2>
            <Button variant="icon" size="sm" icon="close" aria-label="Close" onClick={close} />
          </div>
          <p className="popover__body">{children}</p>
        </div>
      )}
    </span>
  );
}
