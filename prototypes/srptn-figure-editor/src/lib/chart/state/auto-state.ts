import type { TableSchema, VegaType } from "../schema/table-schema";
import type { ChartState } from "./types";
import { createInitialState } from "./types";

export function autoState(table: TableSchema): ChartState {
  const state = createInitialState("point");
  const columns = table.columns;
  if (columns.length === 0) {
    return state;
  }

  const x =
    columns.find((column) => column.type === "temporal") ??
    columns.find((column) => column.type === "quantitative") ??
    columns[0];
  const y =
    columns.find(
      (column) => column.name !== x.name && column.type === "quantitative",
    ) ??
    columns.find(
      (column) => column.name !== x.name && column.type === "temporal",
    ) ??
    columns.find((column) => column.name !== x.name);
  const color =
    columns.find(
      (column) =>
        column.name !== x.name &&
        column.name !== y?.name &&
        (column.type === "nominal" || column.type === "ordinal"),
    ) ?? undefined;

  const layer = state.layers[0];
  layer.encoding.x = { field: x.name, type: x.type as VegaType };
  if (y) {
    layer.encoding.y = { field: y.name, type: y.type as VegaType };
  }
  if (color) {
    layer.encoding.color = { field: color.name, type: color.type as VegaType };
  }
  return state;
}
