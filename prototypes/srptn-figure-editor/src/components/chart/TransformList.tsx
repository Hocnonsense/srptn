import { useChartStore } from "../../lib/chart/state/chart-store";
import type { Scope } from "../../lib/chart/state/types";
import { collectAggregateOps } from "../../lib/chart/engine/aggregate";
import { unusedOutputs } from "../../lib/chart/engine/usage";
import {
  createDerivedTransform,
  makeFilterTransform,
  readDerivedTransform,
} from "../../lib/chart/engine/transforms";
import { AggregateRow } from "./AggregateRow";
import { DeriveRow } from "./DeriveRow";
import { FilterRow } from "./FilterRow";
import { RowList } from "./Rows";
import "./TransformList.css";

export function TransformList({ scope = "layer" }: { scope?: Scope }) {
  const table = useChartStore((store) => store.table);
  const state = useChartStore((store) => store.state);
  const activeLayerIndex = useChartStore((store) => store.activeLayerIndex);
  const layer = state.layers[activeLayerIndex] ?? state.layers[0];
  const transforms = scope === "shared" ? state.shared.transform : layer.transform;
  const unused = unusedOutputs(state, scope, activeLayerIndex);
  const addTransform = useChartStore((store) => store.addTransform);
  const addAggregate = useChartStore((store) => store.addAggregate);

  const first = table.columns[0];

  const addFilter = () => {
    if (!first) {
      return;
    }
    const value =
      first.sampleValues.find((item) => item !== null && item !== undefined) ??
      (first.type === "quantitative" ? 0 : "");
    addTransform(
      makeFilterTransform(
        { field: first.name, op: "==", value: String(value) },
        first.type,
      ),
      scope,
    );
  };

  const firstQuantitative = table.columns.find(
    (column) => column.type === "quantitative",
  );
  const firstTemporal = table.columns.find(
    (column) => column.type === "temporal",
  );

  const addDerive = () => {
    if (!first) {
      return;
    }
    addTransform(
      createDerivedTransform("calculate", { field: first.name }),
      scope,
    );
  };

  const fieldsBefore = (index: number): Map<string, string> => {
    const fields = new Map<string, string>(
      table.columns.map((column) => [column.name, column.type]),
    );
    for (let itemIndex = 0; itemIndex < index; itemIndex += 1) {
      const transform = transforms[itemIndex];
      const derived = readDerivedTransform(transform);
      for (const output of collectAggregateOps([transform])) {
        fields.set(output.name, "aggregate");
      }
      if (derived) {
        fields.set(derived.as, derived.kind);
      }
    }
    return fields;
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <div className="chip-row">
          <button className="chip" onClick={addFilter} disabled={!first}>
            + Filter
          </button>
          <button
            className="chip"
            onClick={addDerive}
            disabled={!first}
          >
            + Derive
          </button>
          <button
            className="chip"
            onClick={() => addAggregate(scope)}
            disabled={!first}
          >
            + Aggregate
          </button>
        </div>
        <h3>{scope === "shared" ? "Shared transforms" : "Layer transforms"}</h3>
      </div>
      {transforms.length === 0 ? (
        <p className="muted">
          {scope === "shared" ? "Applied before encoding. Add a filter, aggregate, or derive transform to start." : ""}
        </p>
      ) : (
        <RowList>
          {transforms.map((transform, index) => {
            if (Array.isArray(transform.aggregate)) {
              const availableFields = fieldsBefore(index);
              return transform.aggregate.map((entry, opIndex) => (
                <AggregateRow
                  key={`${index}-${opIndex}`}
                  transform={transform}
                  index={index}
                  opIndex={opIndex}
                  entry={entry}
                  scope={scope}
                  availableFields={availableFields}
                  unused={unused}
                />
              ));
            }

            const derived = readDerivedTransform(transform);
            if (derived) {
              return (
                <DeriveRow
                  key={index}
                  transform={transform}
                  index={index}
                  scope={scope}
                  availableFields={fieldsBefore(index)}
                  output={derived.as}
                  unused={unused}
                  firstField={first?.name}
                  firstQuantitative={firstQuantitative?.name}
                  firstTemporal={firstTemporal?.name}
                />
              );
            }

            return (
              <FilterRow
                key={index}
                transform={transform}
                index={index}
                scope={scope}
                columns={table.columns}
              />
            );
          })}
        </RowList>
      )}
    </section>
  );
}
