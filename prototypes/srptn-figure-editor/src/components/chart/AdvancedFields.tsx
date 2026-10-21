import { useEffect, useState } from "react";

import type { ChartState } from "../../lib/chart/state/types";
import {
  getAtPath,
  setAtPath,
  unsupportedPaths,
} from "../../lib/chart/engine/specEditor";
import { Field } from "./Field";
import { Row, RowList } from "./Rows";
import "./AdvancedFields.css";

export function AdvancedFields({
  state,
  onApply,
}: {
  state: ChartState;
  onApply: (state: ChartState) => void;
}) {
  const paths = unsupportedPaths(state);
  if (paths.length === 0) {
    return null;
  }

  return (
    <details className="panel advanced-panel">
      <summary>
        <span>Advanced spec fields</span>
        <span className="muted">{paths.length} from imported spec</span>
      </summary>
      <RowList>
        {paths.map((path) => (
          <AdvancedField
            key={path}
            path={path}
            value={getAtPath(state, path)}
            onChange={(value) => onApply(setAtPath(state, path, value))}
          />
        ))}
      </RowList>
    </details>
  );
}

function AdvancedField({
  path,
  value,
  onChange,
}: {
  path: string;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!dirty) {
      setText(JSON.stringify(value, null, 2));
    }
  }, [value, dirty]);

  const apply = () => {
    try {
      const parsed = JSON.parse(text);
      onChange(parsed);
      setDirty(false);
      setError(undefined);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : String(exception));
    }
  };

  return (
    <Row className="advanced-row">
      <Field label={path} error={error}>
        <textarea
          className="field-textarea"
          value={text}
          spellCheck={false}
          onChange={(event) => {
            setText(event.target.value);
            setDirty(true);
          }}
          onBlur={apply}
        />
      </Field>
    </Row>
  );
}
