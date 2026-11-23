import type { ReactNode } from "react";

// Paths are copied from the design's icon board: 24 px grid, drawn with a 1.5 stroke in the
// current colour (see .icon in styles/base.css). They are JSX, never an HTML string, because a
// string would have to be injected as markup (§4.4). Icons are decoration: the word beside each
// one carries the meaning, so every icon is hidden from assistive technology.
const PATHS = {
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </>
  ),
  "x-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </>
  ),
  "alert-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5M12 16.5h.01" />
    </>
  ),
  "alert-triangle": (
    <>
      <path d="M10.3 4.9 2.6 18.2A2 2 0 0 0 4.3 21h15.4a2 2 0 0 0 1.7-2.8L13.7 4.9a2 2 0 0 0-3.4 0z" />
      <path d="M12 9.5v4.5M12 17.5h.01" />
    </>
  ),
  spinner: (
    <>
      <circle cx="12" cy="12" r="8" opacity="0.3" />
      <path d="M20 12a8 8 0 0 0-8-8" />
    </>
  ),
  "chevron-right": <path d="M9.5 6l6 6-6 6" />,
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8.5" />
      <path d="M20 4v4.5h-4.5" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className={name === "spinner" ? "icon spin" : "icon"} viewBox="0 0 24 24" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}
