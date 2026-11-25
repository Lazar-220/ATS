import type { ReactNode } from "react";

import { Icon } from "./Icon";
import "./Banner.css";

// A note that holds for the whole screen: the rubric behind its numbers is not confirmed yet.
export function ProvisionalBanner({ children }: { children: ReactNode }) {
  return (
    <div className="banner" role="note">
      <Icon name="alert-triangle" />
      <div>
        <span className="banner__title">Provisional</span>
        {children}
      </div>
    </div>
  );
}
