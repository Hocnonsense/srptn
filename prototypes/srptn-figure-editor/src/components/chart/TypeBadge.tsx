import type { VegaType } from "../../lib/chart/schema/table-schema";
import { VEGA_TYPE_META } from "../../lib/chart/schema/table-schema";

export function TypeBadge({ type }: { type?: VegaType }) {
  if (!type) {
    return null;
  }
  const { label, ...style } = VEGA_TYPE_META[type];
  return (
    <span className="type-badge" style={style}>
      {label}
    </span>
  );
}
