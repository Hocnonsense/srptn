import type { ColumnProfile } from "../../lib/chart/schema/table-schema";
import {
  FILTER_OPS,
  makeFilterTransform,
  readFilterTransform,
} from "../../lib/chart/engine/transforms";
import { useChartStore } from "../../lib/chart/state/chart-store";
import type { Scope } from "../../lib/chart/state/types";
import { Row } from "./Rows";

interface FilterRowProps {
  transform: Record<string, unknown>;
  index: number;
  scope: Scope;
  columns: readonly ColumnProfile[];
}

export function FilterRow({
  transform,
  index,
  scope,
  columns,
}: FilterRowProps) {
  const updateTransform = useChartStore((store) => store.updateTransform);
  const removeTransform = useChartStore((store) => store.removeTransform);
  const filter = readFilterTransform(transform);
  const column = columns.find((item) => item.name === filter?.field);

  return (
    <Row className="transform-row">
      <button
        type="button"
        className="icon-button"
        title="Remove transform"
        onClick={() => removeTransform(index, scope)}
      > × </button>
      <span className="transform-kind">
        {filter ? "Filter" : "Transform"}
      </span>
      {filter && column ? (
        <>
          <select
            value={filter.field}
            onChange={(event) => {
              const nextColumn = columns.find(
                (item) => item.name === event.target.value,
              );
              updateTransform(
                index,
                makeFilterTransform(
                  {
                    field: event.target.value,
                    op: filter.op,
                    value: filter.value,
                  },
                  nextColumn?.type ?? "nominal",
                ),
                scope,
              );
            }}
          >
            {columns.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.type})
              </option>
            ))}
          </select>
          <select
            value={filter.op}
            onChange={(event) =>
              updateTransform(
                index,
                makeFilterTransform(
                  { ...filter, op: event.target.value },
                  column.type,
                ),
                scope,
              )
            }
          >
            {FILTER_OPS.map((op) => (
              <option key={op.value} value={op.value}>
                {op.label}
              </option>
            ))}
          </select>
          <input
            value={filter.value}
            onChange={(event) =>
              updateTransform(
                index,
                makeFilterTransform(
                  { ...filter, value: event.target.value },
                  column.type,
                ),
                scope,
              )
            }
          />
        </>
      ) : (
        <code className="transform-raw">{JSON.stringify(transform)}</code>
      )}
    </Row>
  );
}
