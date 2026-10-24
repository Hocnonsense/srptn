import { useEffect, useState } from "react";

import type { ChartState } from "../../lib/chart/state/types";
import {
  LOCKED_DATA,
  editableSpecText,
  parseEditableSpec,
  vegaEditorUrl,
} from "../../lib/chart/engine/specEditor";
import "./SpecEditor.css";

export function SpecEditor({
  spec,
  exportSpec,
  onApply,
  onEditingChange,
  disabled = false,
}: {
  spec: Record<string, unknown>;
  exportSpec: Record<string, unknown>;
  onApply: (state: ChartState) => void;
  onEditingChange?: (editing: boolean) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(() => editableSpecText(spec));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string>();
  const [unsupported, setUnsupported] = useState<string[]>([]);

  useEffect(() => {
    if (!open && !dirty) {
      setText(editableSpecText(spec));
    }
  }, [spec, open, dirty]);

  const openEditor = () => {
    if (disabled) {
      return;
    }
    setText(editableSpecText(spec));
    setDirty(false);
    setError(undefined);
    setUnsupported([]);
    setOpen(true);
    onEditingChange?.(true);
  };

  const closeAndApply = () => {
    const result = parseEditableSpec(text);
    if (result.error || !result.state) {
      setError(result.error ?? "Spec could not be applied.");
      setUnsupported(result.unsupported);
      return false;
    }
    onApply(result.state);
    setError(undefined);
    setUnsupported(result.unsupported);
    setDirty(false);
    setOpen(false);
    onEditingChange?.(false);
    return true;
  };

  const toggle = () => {
    if (disabled) {
      return;
    }
    if (open) {
      closeAndApply();
    } else {
      openEditor();
    }
  };

  const reset = () => {
    setText(editableSpecText(spec));
    setDirty(false);
    setError(undefined);
  };

  const openInVegaEditor = () => {
    window.open(vegaEditorUrl(exportSpec), "_blank", "noopener,noreferrer");
  };

  return (
    <section
      className={`panel panel-stack spec-block ${open ? "is-open" : ""}`}
    >
      <button
        type="button"
        className="panel-toggle spec-toggle"
        onClick={toggle}
        disabled={disabled}
      >
        <span>Save spec</span>
        <span className="muted">
          {open ? "collapse & apply" : "expand to edit"}
        </span>
      </button>
      {open ? (
        <>
          <p className="spec-note">
            Editing locks the other controls. Collapsing applies the spec and
            replaces the graphical editor state. <code>data</code> is locked as{" "}
            <code>"{LOCKED_DATA}"</code>.
          </p>
          <textarea
            className="spec-textarea"
            value={text}
            spellCheck={false}
            onChange={(event) => {
              setText(event.target.value);
              setDirty(true);
            }}
          />
          {error && <pre className="spec-error">{error}</pre>}
          {unsupported.length > 0 && (
            <div className="spec-warning">
              <strong>Unsupported fields preserved in the spec</strong>
              <ul>
                {unsupported.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="spec-actions">
            <button type="button" onClick={() => closeAndApply()}>
              Apply & collapse
            </button>
            <button type="button" onClick={reset}>
              Reset
            </button>
            <button type="button" onClick={openInVegaEditor}>
              Open in Vega editor
            </button>
          </div>
        </>
      ) : (<p />)}
    </section>
  );
}
