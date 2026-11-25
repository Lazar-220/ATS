import "./AddModeChip.css";
import { Button } from "./Button";
import "./FileField.css";
import { Icon } from "./Icon";

type AddModeChipProps = {
  filename: string;
  disabled: boolean;
  onLeave: () => void;
};

// Stands where the posting field was, under the same label: the posting is already chosen. The
// name comes from an uploaded file, so it is text only (§4.4); `title` shows it in full when the
// chip cuts it off.
export function AddModeChip({ filename, disabled, onLeave }: AddModeChipProps) {
  return (
    <div className="field chip-field">
      <span className="label">Job posting (PDF)</span>
      <span className="chip">
        <Icon name="file" />
        <span className="chip__text" title={`Adding CVs to ${filename}`}>
          Adding CVs to <b>{filename}</b>
        </span>
        <Button variant="icon" size="sm" icon="close" aria-label="Stop adding CVs" disabled={disabled} onClick={onLeave} />
      </span>
    </div>
  );
}
