import { describe, expect, it } from "vitest";

import {
  VEGA_TYPES,
  inferTableSchema,
  inferValueType,
  isVegaType,
} from "./table-schema";
import { enumOf } from "./vl-schema";

describe("table schema", () => {
  it("infers column profiles from rows", () => {
    const schema = inferTableSchema([
      { group: "A", value: 1, date: "2026-01-01", ok: true },
      { group: "B", value: 3, date: "2026-01-02", ok: false },
      { group: null, value: null, date: null, ok: true },
    ]);

    expect(schema.columns.map((column) => column.name)).toEqual([
      "date",
      "group",
      "ok",
      "value",
    ]);
    expect(schema.columns.find((column) => column.name === "date")).toMatchObject(
      {
        type: "temporal",
        minimum: "2026-01-01",
        maximum: "2026-01-02",
        nullable: true,
      },
    );
    expect(schema.columns.find((column) => column.name === "group")).toMatchObject(
      {
        type: "nominal",
        distinctCount: 2,
        nullable: true,
      },
    );
    expect(schema.columns.find((column) => column.name === "value")).toMatchObject(
      {
        type: "quantitative",
        minimum: 1,
        maximum: 3,
      },
    );
  });

  it("keeps VegaType aligned with the pinned schema", () => {
    const schemaTypes = enumOf("#/definitions/StandardType");
    const expected = ["nominal", "ordinal", "quantitative", "temporal"];

    expect([...schemaTypes].sort()).toEqual(expected);
    expect([...VEGA_TYPES].sort()).toEqual(expected);
    for (const type of schemaTypes) {
      expect(isVegaType(type)).toBe(true);
    }
    expect(isVegaType("geojson")).toBe(false);
  });

  it("classifies scalar values", () => {
    expect(inferValueType(1)).toBe("quantitative");
    expect(inferValueType("2026-01-01")).toBe("temporal");
    expect(inferValueType("A")).toBe("nominal");
    expect(inferValueType(true)).toBe("nominal");
    expect(inferValueType(null)).toBeUndefined();
  });
});
