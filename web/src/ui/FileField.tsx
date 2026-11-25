import { useId } from "react";

import "./FileField.css";

type FileFieldProps = {
  label: string;
  multiple?: boolean;
  disabled: boolean;
  invalid: boolean;
  onChange: (files: File[]) => void;
};

// The native file input, so the browser supplies the button and the file count. It points at
// #form-msg, the one message area of the upload form.
export function FileField({ label, multiple = false, disabled, invalid, onChange }: FileFieldProps) {
  const id = useId();
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <div className="file">
        <input
          id={id}
          type="file"
          accept="application/pdf,.pdf"
          multiple={multiple}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby="form-msg"
          onChange={(event) => onChange(Array.from(event.target.files ?? []))}
        />
      </div>
    </div>
  );
}
