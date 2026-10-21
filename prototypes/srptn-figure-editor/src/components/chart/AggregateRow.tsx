import { AGGREGATE_OPS } from "../../lib/chart/metamodel/rules";
import { aggregateName } from "../../lib/chart/engine/aggregate";
import { useChartStore } from "../../lib/chart/state/chart-store";
import type { Scope } from "../../lib/chart/state/types";
import { Row } from "./Rows";

interface AggregateRowProps {
  transform: Record<string, unknown>;
  index: number;
  opIndex: number;
  entry: unknown;
  scope: Scope;
  availableFields: Map<string, string>;
  unused: Set<string>;
}

export function AggregateRow({
  transform,
  index,
  opIndex,
  entry,
  scope,
  availableFields,
  unused,
}: AggregateRowProps) {
  const updateTransform = useChartStore((store) => store.updateTransform);
  const removeTransform = useChartStore((store) => store.removeTransform);
  const renameField = useChartStore((store) => store.renameField);
  const ops = Array.isArray(transform.aggregate)
    ? transform.aggregate
    : [];

  if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
    return null;
  }
  const item = entry as Record<string, unknown>;
  const op = typeof item.op === "string" ? item.op : "count";
  const field = typeof item.field === "string" ? item.field : "";
  const fieldOptions = new Map(availableFields);
  if (field && !fieldOptions.has(field)) {
    fieldOptions.set(field, "field");
  }
  const update = (patch: Record<string, unknown>) => {
    const nextOp = typeof patch.op === "string" ? patch.op : op;
    const nextField =
      "field" in patch
        ? typeof patch.field === "string" && patch.field
          ? patch.field
          : undefined
        : typeof item.field === "string"
          ? item.field
          : undefined;
    const nextName = aggregateName(nextOp, nextField);
    const next = ops.map((current, currentIndex) =>
      currentIndex === opIndex ? { ...item, ...patch, as: nextName } : current,
    );
    updateTransform(index, { ...transform, aggregate: next }, scope);
    if (typeof item.as === "string" && item.as !== nextName) {
      renameField(item.as, nextName, scope);
    }
  };
  const remove = () => {
    const next = ops.filter((_, currentIndex) => currentIndex !== opIndex);
    if (next.length === 0) {
      removeTransform(index, scope);
      return;
    }
    updateTransform(index, { ...transform, aggregate: next }, scope);
  };

  return (
    <Row
      className={
        `transform-row transform-row-calculate` +
        (typeof item.as === "string" && unused.has(item.as) ? " unused" : "")
      }
    >
      <button
        type="button"
        className="icon-button"
        title="Remove aggregate"
        onClick={remove}
      > × </button>
      <span className="transform-kind">Aggregate</span>
      <select
        value={op}
        onChange={(event) => update({ op: event.target.value })}
      >
        {AGGREGATE_OPS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <select
        value={field}
        onChange={(event) =>
          update({ field: event.target.value || undefined })
        }
      >
        <option value="">—</option>
        {[...fieldOptions].map(([name, type]) => (
          <option key={name} value={name}>
            {name} ({type})
          </option>
        ))}
      </select>
    </Row>
  );
}
