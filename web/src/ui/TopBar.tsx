import { href } from "../route";
import { HealthLine, type HealthLineProps } from "./HealthLine";
import "./TopBar.css";

// No sidebar: the brand goes home and the health line sits at the right.
export function TopBar({ health }: { health: HealthLineProps }) {
  return (
    <header className="topbar">
      <a className="topbar__brand" href={href({ name: "positions" })}>
        ATS
      </a>
      <span className="topbar__spacer" />
      <HealthLine {...health} />
    </header>
  );
}
