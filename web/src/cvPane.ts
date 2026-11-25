import type { Segment } from "./highlight";

// 0 plain, 1 part of a verified quote, 2 part of the selected requirement's quote.
export type Level = 0 | 1 | 2;

export interface Run {
  text: string;
  level: Level;
}

// Joins neighbouring segments that look the same, so a quote that overlaps another one is drawn
// as one highlight with one outline. Where two quotes overlap, the selected style wins.
export function highlightRuns(segments: Segment[], selectedId: string | null): Run[] {
  const runs: Run[] = [];
  for (const part of segments) {
    let level: Level = part.ids.length === 0 ? 0 : 1;
    if (selectedId !== null && part.ids.includes(selectedId)) {
      level = 2;
    }
    const last = runs.at(-1);
    if (last?.level === level) {
      last.text += part.text;
    } else {
      runs.push({ text: part.text, level });
    }
  }
  return runs;
}

export interface PaneGeometry {
  scrollTop: number;
  // Viewport coordinates of the top of the pane's visible area and of the mark.
  paneTop: number;
  paneHeight: number;
  markTop: number;
  markHeight: number;
}

// The scroll position of the pane that puts the mark in its middle. A mark taller than the pane
// starts at the top, so the beginning of the quote is what is read first.
export function centredScrollTop({ scrollTop, paneTop, paneHeight, markTop, markHeight }: PaneGeometry): number {
  const margin = Math.max(0, (paneHeight - markHeight) / 2);
  return Math.max(0, scrollTop + (markTop - paneTop) - margin);
}
