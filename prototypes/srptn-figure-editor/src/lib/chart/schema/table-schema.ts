import { enumOf } from "./vl-schema";

export type VegaType = "quantitative" | "temporal" | "ordinal" | "nominal";

export const VEGA_TYPES = enumOf("#/definitions/StandardType") as VegaType[];

export const VEGA_TYPE_META = {
  quantitative: { label: "Q", background: "#dbeafe", color: "#1d4ed8" },
  temporal: { label: "T", background: "#dcfce7", color: "#15803d" },
  ordinal: { label: "O", background: "#fef3c7", color: "#b45309" },
  nominal: { label: "N", background: "#f3e8ff", color: "#7e22ce" },
} as const satisfies Record<VegaType, { label: string; background: string; color: string }>;

export interface ColumnProfile {
  name: string;
  type: VegaType;
  nullable: boolean;
  distinctCount?: number;
  minimum?: number | string;
  maximum?: number | string;
  sampleValues: unknown[];
  uniqueValues?: unknown[];
}

export interface TableSchema {
  columns: ColumnProfile[];
  rows: Record<string, unknown>[];
}

const ISO_DATE =
  /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

export function isVegaType(value: string): value is VegaType {
  return Object.hasOwn(VEGA_TYPE_META, value);
}

export function inferValueType(value: unknown): VegaType | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (value instanceof Date) {
    return "temporal";
  }
  if (typeof value === "number") {
    return "quantitative";
  }
  if (typeof value === "boolean") {
    return "nominal";
  }
  if (typeof value === "string") {
    if (ISO_DATE.test(value)) {
      return "temporal";
    }
    return "nominal";
  }
  return undefined;
}

export function inferTableSchema(
  rows: Record<string, unknown>[],
): TableSchema {
  const names = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row))),
  ).sort();

  const columns = names.map((name): ColumnProfile => {
    const values = rows.map((row) => row[name]);
    const nonNull = values.filter(
      (value) => value !== null && value !== undefined && value !== "",
    );
    const types = nonNull
      .map(inferValueType)
      .filter((value): value is VegaType => value !== undefined);
    const type = types.length > 0 ? types[0] : "nominal";
    const unique = Array.from(new Set(nonNull));
    const numeric = nonNull.filter(
      (value): value is number => typeof value === "number",
    );
    const temporal = nonNull
      .filter((value) => value instanceof Date || typeof value === "string")
      .map((value) => (value instanceof Date ? value.toISOString() : value))
      .filter((value) => ISO_DATE.test(value))
      .sort();

    return {
      name,
      type,
      nullable: nonNull.length !== values.length,
      distinctCount: unique.length,
      minimum:
        type === "quantitative" && numeric.length > 0
          ? Math.min(...numeric)
          : type === "temporal" && temporal.length > 0
            ? temporal[0]
            : undefined,
      maximum:
        type === "quantitative" && numeric.length > 0
          ? Math.max(...numeric)
          : type === "temporal" && temporal.length > 0
            ? temporal[temporal.length - 1]
            : undefined,
      // TODO: Value: count of top 8
      sampleValues: nonNull.slice(0, 8),
      uniqueValues:
        (type === "nominal" || type === "ordinal") && unique.length <= 50
          ? unique
          : undefined,
    };
  });

  return { columns, rows };
}

export function columnMap(schema: TableSchema): Map<string, ColumnProfile> {
  return new Map(schema.columns.map((column) => [column.name, column]));
}

export function tableFromColumns(
  columns: { name: string; type: VegaType }[],
  rows: Record<string, unknown>[],
): TableSchema {
  const inferred = columnMap(inferTableSchema(rows));
  return {
    rows,
    columns: columns.map((column) => ({
      ...(inferred.get(column.name) ?? {
        name: column.name,
        nullable: true,
        sampleValues: [],
      }),
      name: column.name,
      type: column.type,
    })),
  };
}
