import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

import { Icon } from "./Icon";
import "./Inputs.css";

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "type"> & { invalid: boolean };

export function TextInput({ invalid, ...rest }: InputProps) {
  return <input {...rest} type="text" className="input" aria-invalid={invalid || undefined} />;
}

export function NumberInput({ invalid, ...rest }: InputProps) {
  return <input {...rest} type="number" className="input input--num" aria-invalid={invalid || undefined} />;
}

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "className"> & { invalid: boolean };

// The native select, with the browser's arrow replaced by the design's icon.
export function Select({ invalid, children, ...rest }: SelectProps) {
  return (
    <span className="select-wrap">
      <select {...rest} className="select" aria-invalid={invalid || undefined}>
        {children}
      </select>
      <Icon name="chevron-down" />
    </span>
  );
}
