import { Fragment } from "react";

import {
  DERIVE_SPECS,
  createDerivedTransform,
  isDeriveKind,
  readDerivedTransform,
  updateDerivedTransform,
} from "../../lib/chart/engine/transforms";
import type { DeriveControl } from "../../lib/chart/engine/transforms";
import { useChartStore } from "../../lib/chart/state/chart-store";
import type { Scope } from "../../lib/chart/state/types";
import { ParamControl } from "./ParamControl";
import { Row } from "./Rows";

interface DeriveRowProps {
  transform: Record<string, unknown>;
  index: number;
  scope: Scope;
  availableFields: Map<string, string>;
  output: string;
  unused: Set<string>;
  firstField?: string;
  firstQuantitative?: string;
  firstTemporal?: string;
}

export function DeriveRow({
  transform,
  index,
  scope,
  availableFields,
  output,
  unused,
  firstField,
  firstQuantitative,
  firstTemporal,
}: DeriveRowProps) {
  const updateTransform = useChartStore((store) => store.updateTransform);
  const removeTransform = useChartStore((store) => store.removeTransform);
  const renameField = useChartStore((store) => store.renameField);
  const derived = readDerivedTransform(transform);
  if (!derived) {
    return null;
  }
  const kind = derived.kind;

  const updateDerived = (patch: Record<string, unknown>) => {
    const next = updateDerivedTransform(derived.kind, transform, patch);
    if (!next) {
      return;
    }
    updateTransform(index, next, scope);
    const nextOutput = readDerivedTransform(next)?.as;
    if (output && nextOutput && output !== nextOutput) {
      renameField(output, nextOutput, scope);
    }
  };

  const switchKind = (nextKind: string) => {
    if (!isDeriveKind(nextKind) || nextKind === kind) {
      return;
    }
    const next = createDerivedTransform(nextKind, {
      field: derived.sourceField ?? firstField ?? "",
      quantitativeField: firstQuantitative,
      temporalField: firstTemporal,
    });
    updateTransform(index, next, scope);
    const nextOutput = readDerivedTransform(next)?.as;
    if (output && nextOutput && output !== nextOutput) {
      renameField(output, nextOutput, scope);
    }
  };

  const renderControl = (control: DeriveControl) => {
    const value = (derived.state as unknown as Record<string, unknown>)[
      control.key
    ];
    if (control.kind === "field") {
      return (
        <select
          value={typeof value === "string" ? value : ""}
          onChange={(event) =>
            updateDerived({ [control.key]: event.target.value })
          }
        >
          {[...availableFields].map(([name, type]) => (
            <option key={name} value={name}>
              {name} ({type})
            </option>
          ))}
        </select>
      );
    }
    return (
      <ParamControl
        control={control}
        value={value}
        onChange={(next) => updateDerived({ [control.key]: next })}
      />
    );
  };

  return (
    <Row
      className={`transform-row transform-row-derive ${unused.has(output) ? "unused" : ""}`}
    >
      <button
        type="button"
        className="icon-button"
        title="Remove derive"
        onClick={() => removeTransform(index, scope)}
      > × </button>
      <span className="transform-kind">Derive</span>
      <select
        value={kind}
        onChange={(event) => switchKind(event.target.value)}
      >
        {Object.keys(DERIVE_SPECS).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <div className="derive-params">
        {derived.controls.map((control) => (
          <Fragment key={control.key}>{renderControl(control)}</Fragment>
        ))}
      </div>
    </Row>
  );
}
