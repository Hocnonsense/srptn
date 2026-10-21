import { VEGA_TYPE_META, columnMap } from "../schema/table-schema";
import type { TableSchema, VegaType } from "../schema/table-schema";
import type { ChartState, LayerState, Scope } from "../state/types";
import { fieldStatus } from "../metamodel/rules";

export interface ChoiceOption {
  value: string | number | boolean;
  label: string;
  description?: string;
  disabled?: boolean;
  reason?: string;
  group?: string;
}

export interface OptionContext {
  channel: string;
  table: TableSchema;
  state: ChartState;
  layerIndex: number;
  layer: LayerState;
  scope: Scope;
}

export function resolveOptions(context: OptionContext): ChoiceOption[] {
  const { channel, state, layer, table, scope } = context;
  const columns = columnMap(table);
  return table.columns
    .map((column): ChoiceOption => {
      const rule =
        scope === "shared"
          ? sharedFieldStatus(state, channel as never, column.type)
          : fieldStatus(layer.mark, channel as never, column.type);
      return {
        value: column.name,
        label: `${column.name} (${VEGA_TYPE_META[column.type].label})`,
        description: `${column.type}${column.nullable ? ", nullable" : ""}`,
        disabled: rule.status === "invalid",
        reason: rule.reason,
      };
    })
    .sort((left, right) => {
      if (Boolean(left.disabled) !== Boolean(right.disabled)) {
        return left.disabled ? 1 : -1;
      }
      const leftColumn = columns.get(String(left.value));
      const rightColumn = columns.get(String(right.value));
      return (leftColumn?.name ?? "").localeCompare(rightColumn?.name ?? "");
    });
}

function sharedFieldStatus(
  state: ChartState,
  channel: Parameters<typeof fieldStatus>[1],
  type: VegaType,
): ReturnType<typeof fieldStatus> {
  let warning: ReturnType<typeof fieldStatus> | undefined;
  let invalid: ReturnType<typeof fieldStatus> | undefined;
  for (const layer of state.layers) {
    const rule = fieldStatus(layer.mark, channel, type);
    if (rule.status === "available") {
      return rule;
    }
    if (rule.status === "warning") {
      warning = rule;
    } else if (!invalid) {
      invalid = rule;
    }
  }
  return warning ?? invalid ?? { status: "available" };
}
