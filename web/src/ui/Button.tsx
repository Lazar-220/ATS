import type { ButtonHTMLAttributes, KeyboardEvent, MouseEvent } from "react";

import "./Button.css";
import { Icon, type IconName } from "./Icon";

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
  variant: "primary" | "secondary" | "ghost" | "icon";
  size?: "md" | "sm";
  icon?: IconName;
  // Shows a spinner in place of the icon; the caller keeps the label text, so the word stays.
  busy?: boolean;
  // Looks disabled but stays focusable, so a tooltip can still be reached by keyboard. Native
  // `disabled` would drop the button from the tab order.
  ariaDisabled?: boolean;
  // An icon button that takes something away turns red under the pointer.
  danger?: boolean;
};

export function Button({
  variant,
  size = "md",
  icon,
  busy = false,
  ariaDisabled = false,
  danger = false,
  type = "button",
  onClick,
  onKeyDown,
  children,
  ...rest
}: ButtonProps) {
  const classes = ["btn", `btn--${variant}`, size === "sm" ? "btn--sm" : "", danger ? "btn--danger-icon" : ""]
    .filter(Boolean)
    .join(" ");

  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    if (ariaDisabled) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (ariaDisabled) {
      // Enter and Space would turn into a click; the click handler also ignores it, this keeps
      // the key from reaching any handler the caller passed.
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
      }
      return;
    }
    onKeyDown?.(event);
  }

  return (
    <button
      {...rest}
      type={type}
      className={classes}
      aria-busy={busy || undefined}
      aria-disabled={ariaDisabled || undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {busy ? <Icon name="spinner" /> : icon && <Icon name={icon} />}
      {children}
    </button>
  );
}
