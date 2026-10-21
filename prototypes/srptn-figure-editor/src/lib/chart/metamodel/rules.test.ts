import { describe, expect, it } from "vitest";

import { enumOf, schemaAt } from "../schema/vl-schema";
import {
  AGGREGATE_OPS,
  CHANNELS,
  FACET_CHANNELS,
  SCALE_TYPES_BY_FIELD_TYPE,
  fieldStatus,
  guideForChannel,
  markChannelRule,
  scaleTypes,
} from "./rules";

function propertyKeys(reference: string): string[] {
  return Object.keys(schemaAt(reference)?.properties ?? {});
}

describe("chart rules", () => {
  it("filters only channels that really depend on mark", () => {
    expect(markChannelRule("point", "shape").status).toBe("available");
    expect(markChannelRule("line", "shape").status).toBe("invalid");
    expect(markChannelRule("text", "text").status).toBe("available");
    expect(markChannelRule("point", "text").status).toBe("invalid");
    expect(markChannelRule("arc", "theta").status).toBe("available");
    expect(markChannelRule("bar", "x2").status).toBe("available");
    expect(FACET_CHANNELS.has("column")).toBe(true);
    expect(CHANNELS).not.toContain("column");
  });

  it("checks field types against channels", () => {
    expect(fieldStatus("point", "shape", "nominal").status).toBe("available");
    expect(fieldStatus("point", "shape", "quantitative").status).toBe(
      "invalid",
    );
    expect(fieldStatus("line", "size", "quantitative").status).toBe(
      "available",
    );
  });

  it("maps guides by channel kind", () => {
    expect(guideForChannel("x")).toBe("axis");
    expect(guideForChannel("color")).toBe("legend");
    expect(guideForChannel("theta")).toBe("legend");
    expect(guideForChannel("theta2")).toBe("none");
    expect(guideForChannel("column")).toBe("header");
    expect(guideForChannel("tooltip")).toBe("none");
  });

  it("derives scale types from field type and channel", () => {
    expect(scaleTypes("x", "quantitative")).toContain("log");
    expect(scaleTypes("color", "nominal")).toEqual(["ordinal"]);
    expect(scaleTypes("color", "quantitative")).toContain("sequential");
  });

  it("keeps curated channels inside the schema", () => {
    const encoding = new Set([
      ...propertyKeys("#/definitions/Encoding"),
      ...propertyKeys("#/definitions/FacetedEncoding"),
    ]);
    const faceted = new Set(propertyKeys("#/definitions/FacetedEncoding"));

    expect(CHANNELS.every((channel) => encoding.has(channel))).toBe(true);
    expect([...FACET_CHANNELS].every((channel) => faceted.has(channel))).toBe(
      true,
    );
  });

  it("keeps curated options inside schema enums", () => {
    const aggregateOps = new Set(enumOf("#/definitions/AggregateOp"));
    expect(AGGREGATE_OPS.every((op) => aggregateOps.has(op))).toBe(true);

    const scaleTypes = new Set(enumOf("#/definitions/ScaleType"));
    expect(
      Object.values(SCALE_TYPES_BY_FIELD_TYPE)
        .flat()
        .every((scale) => scaleTypes.has(scale)),
    ).toBe(true);
  });
});
