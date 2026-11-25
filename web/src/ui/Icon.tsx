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
  upload: <path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  file: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5M12 7.75h.01" />
    </>
  ),
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  inbox: (
    <path d="M3.5 13.5 6 5.5A1.5 1.5 0 0 1 7.4 4.5h9.2A1.5 1.5 0 0 1 18 5.5l2.5 8M3.5 13.5V18a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-4.5H15a3 3 0 0 1-6 0z" />
  ),
  "chevron-right": <path d="M9.5 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  "chevron-down": <path d="M6 9.5l6 6 6-6" />,
  trash: (
    <path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.1a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9L17.5 7M10 11v6M14 11v6" />
  ),
  "help-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.3a2.5 2.5 0 0 1 4.9.7c0 1.7-2.5 2.2-2.5 3.6M12 17h.01" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.34-5.66L20 8.5" />
      <path d="M20 4v4.5h-4.5" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size }: { name: IconName; size?: 20 }) {
  const classes = ["icon", name === "spinner" ? "spin" : "", size === 20 ? "icon--20" : ""].filter(Boolean).join(" ");
  return (
    <svg className={classes} viewBox="0 0 24 24" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}
