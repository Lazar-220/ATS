import type { ReactNode } from "react";

import "./Link.css";
import { Icon, type IconName } from "./Icon";

type LinkProps = {
  href: string;
  strong?: boolean;
  trailingIcon?: IconName;
  children: ReactNode;
};

export function Link({ href, strong = false, trailingIcon, children }: LinkProps) {
  return (
    <a className={strong ? "link link--strong" : "link"} href={href}>
      {children}
      {trailingIcon && <Icon name={trailingIcon} />}
    </a>
  );
}
