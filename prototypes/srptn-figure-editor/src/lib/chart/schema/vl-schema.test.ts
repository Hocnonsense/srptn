import { describe, expect, it } from "vitest";

import {
  descOf,
  enumOf,
  fieldsOf,
  rangeOf,
  resolvePointer,
  VL_SCHEMA,
} from "./vl-schema";

describe("Vega-Lite schema pointer helpers", () => {
  it("resolves definitions and enums", () => {
    const mark = resolvePointer(VL_SCHEMA, "#/definitions/Mark");
    expect(mark?.type).toBe("string");
    expect(enumOf("#/definitions/Mark")).toContain("point");
    expect(enumOf("#/definitions/ScaleType")).toContain("linear");
  });

  it("reads descriptions", () => {
    expect(descOf("#/definitions/FacetedEncoding/properties/x")).toContain(
      "X coordinates",
    );
  });

  it("reads ranges through anyOf branches", () => {
    expect(rangeOf("#/definitions/Axis/properties/labelAngle")).toMatchObject({
      minimum: -360,
      maximum: 360,
    });
  });

  it("lists object fields with their schema metadata", () => {
    const bin = fieldsOf("#/definitions/BinTransform");
    expect(bin.find((field) => field.name === "bin")).toMatchObject({
      required: true,
      types: ["boolean", "object"],
    });
    expect(bin.find((field) => field.name === "as")).toMatchObject({
      required: true,
      types: ["string", "array"],
    });

    const maxbins = fieldsOf("#/definitions/BinParams").find(
      (field) => field.name === "maxbins",
    );
    expect(maxbins).toMatchObject({ type: "number", minimum: 2 });

    const timeUnit = fieldsOf("#/definitions/TimeUnitTransform").find(
      (field) => field.name === "timeUnit",
    );
    expect(timeUnit?.required).toBe(true);
    expect(timeUnit?.enum).toContain("yearmonth");
  });
});
