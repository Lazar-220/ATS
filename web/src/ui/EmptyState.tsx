import type { ReactNode } from "react";

import { Icon } from "./Icon";
import "./EmptyState.css";

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <Icon name="inbox" size={20} />
      <span>{children}</span>
    </div>
  );
}
