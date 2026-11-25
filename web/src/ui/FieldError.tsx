import "./FieldError.css";
import { Icon } from "./Icon";

// A problem the user fixes in a form. It has no role: the area around it is the live region.
export function FieldError({ message }: { message: string }) {
  return (
    <div className="field-error">
      <Icon name="alert-circle" />
      <span>{message}</span>
    </div>
  );
}
