import { useId, type Ref } from "react";

import "./FileField.css";

type FileFieldProps = {
  label: string;
  multiple?: boolean;
  disabled: boolean;
  invalid: boolean;
  onChange: (files: File[]) => void;
  // For a caller that has to move focus to the input or empty its selection.
  ref?: Ref<HTMLInputElement>;
};

// The native file input, so the browser supplies the button and the file count. It points at
// #form-msg, the one message area of the upload form.
export function FileField({ label, multiple = false, disabled, invalid, onChange, ref }: FileFieldProps) {
  const id = useId();
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      <div className="file">
        <input
          ref={ref}
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
