import { useEffect, useMemo, useRef } from "react";

import { centredScrollTop, highlightRuns } from "../cvPane";
import { segment, toRanges, type Evidence } from "../highlight";
import "./CvViewer.css";

type CvViewerProps = {
  text: string;
  // Verified evidence only: what is listed here is highlighted.
  quotes: Evidence[];
  selectedId: string | null;
};

// The CV is untrusted text (§4.4): every piece is rendered as a text node.
export function CvViewer({ text, quotes, selectedId }: CvViewerProps) {
  const segments = useMemo(() => segment(text, toRanges(text, quotes)), [text, quotes]);
  const runs = highlightRuns(segments, selectedId);
  const pane = useRef<HTMLPreElement>(null);
  const selected = useRef<HTMLElement | null>(null);

  // Only the pane is scrolled, so the page and the requirement cards stay where they are.
  useEffect(() => {
    const box = pane.current;
    const mark = selected.current;
    if (box === null || mark === null) {
      return;
    }
    const markBox = mark.getBoundingClientRect();
    const top = centredScrollTop({
      scrollTop: box.scrollTop,
      paneTop: box.getBoundingClientRect().top + box.clientTop,
      paneHeight: box.clientHeight,
      markTop: markBox.top,
      markHeight: markBox.height,
    });
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
  }, [selectedId]);

  const firstSelected = runs.findIndex((run) => run.level === 2);
  return (
    // Focusable, so the text can be scrolled with the keyboard.
    <pre className="cv" tabIndex={0} data-testid="cv-text" ref={pane}>
      {runs.map((run, index) =>
        run.level === 0 ? (
          <span key={index}>{run.text}</span>
        ) : (
          <mark
            key={index}
            className={run.level === 2 ? "hl hl--selected" : "hl"}
            ref={index === firstSelected ? selected : undefined}
          >
            {run.text}
          </mark>
        ),
      )}
    </pre>
  );
}
