import { describe, expect, it } from "vitest";

import { inferTableSchema } from "../../schema/table-schema";
import type { ChannelState } from "../../state/types";
import { createInitialState } from "../../state/types";
import type { Candidate } from "../types";
import { createRecommendationProfile } from "../profile";
import {
  aggregationQuality,
  channelExtendedType,
  compassEffectiveness,
  compassScore,
  extendedTypeKey,
  fieldOrderScore,
} from "./index";

const TABLE = inferTableSchema(
  Array.from({ length: 24 }, (_, index) => ({
    group: index % 2 === 0 ? "a" : "b",
    site: index % 3 === 0 ? "s1" : "s2",
    value: index,
    time: `2026-01-${String((index % 9) + 1).padStart(2, "0")}`,
    id: `sample-${index}`,
  })),
);
const PROFILE = createRecommendationProfile(TABLE);

function candidate(
  mark: string,
  encoding: Record<string, ChannelState>,
): Candidate {
  const state = createInitialState(mark);
  state.layers[0].encoding = encoding;
  const fields = Object.values(encoding)
    .map((state) => state.field)
    .filter((field): field is string => typeof field === "string");
  return {
    state,
    fields,
    channels: {},
    mark,
  };
}

function features(
  mark: string,
  encoding: Record<string, ChannelState>,
) {
  return compassEffectiveness(PROFILE, candidate(mark, encoding)).features;
}

describe("CompassQL extended types", () => {
  it("derives extended types from channel state", () => {
    expect(
      extendedTypeKey(
        channelExtendedType({
          field: "value",
          type: "quantitative",
          bin: true,
        }),
      ),
    ).toBe("bin_Q");
    expect(
      extendedTypeKey(
        channelExtendedType({
          field: "time",
          type: "temporal",
          timeUnit: "month",
        }),
      ),
    ).toBe("timeUnit_T");
    expect(
      extendedTypeKey(
        channelExtendedType({
          field: "time",
          type: "temporal",
          timeUnit: "month",
          scale: { type: "band" },
        }),
      ),
    ).toBe("timeUnit_O");
    expect(
      extendedTypeKey(
        channelExtendedType(
          { field: "id", type: "nominal" },
          PROFILE.byName.get("id"),
        ),
      ),
    ).toBe("key");
  });
});

describe("CompassQL scoring", () => {
  const q = { field: "value", type: "quantitative" as const };
  const n = { field: "group", type: "nominal" as const };

  it("scores point higher than line for a raw scatter plot", () => {
    const point = compassEffectiveness(
      PROFILE,
      candidate("point", { x: q, y: { ...q, field: "time" } }),
    ).score;
    const line = compassEffectiveness(
      PROFILE,
      candidate("line", { x: q, y: { ...q, field: "time" } }),
    ).score;

    expect(point).toBeGreaterThan(line);
  });

  it("scores bar higher than line for nominal by quantitative", () => {
    const aggregated = { ...q, aggregate: "mean" as const };
    const bar = compassEffectiveness(
      PROFILE,
      candidate("bar", { x: n, y: aggregated }),
    ).score;
    const line = compassEffectiveness(
      PROFILE,
      candidate("line", { x: n, y: aggregated }),
    ).score;

    expect(bar).toBeGreaterThan(line);
  });

  it("penalizes size on bar marks", () => {
    const scored = features("bar", {
      x: n,
      y: q,
      size: { field: "value", type: "quantitative" },
    });

    expect(scored.some((feature) => feature.type === "SizeChannel")).toBe(true);
  });

  it("uses structural extended types for axis preferences", () => {
    const temporalOnX = compassEffectiveness(
      PROFILE,
      candidate("point", {
        x: { field: "time", type: "temporal" },
        y: q,
      }),
    ).score;
    const temporalOnY = compassEffectiveness(
      PROFILE,
      candidate("point", {
        x: q,
        y: { field: "time", type: "temporal" },
      }),
    ).score;

    expect(temporalOnX).toBeGreaterThan(temporalOnY);
  });

  it("scores aggregation quality by chart shape", () => {
    expect(aggregationQuality(PROFILE, candidate("point", { x: q, y: q }))).toBe(1);
    expect(
      aggregationQuality(
        PROFILE,
        candidate("bar", {
          x: n,
          y: { ...q, aggregate: "mean" },
        }),
      ),
    ).toBe(0.9);
    expect(
      aggregationQuality(
        PROFILE,
        candidate("bar", {
          x: n,
          y: { aggregate: "count", type: "quantitative" },
        }),
      ),
    ).toBe(0.8);
    expect(
      aggregationQuality(
        PROFILE,
        candidate("bar", {
          x: { ...q, bin: true },
          y: { aggregate: "count", type: "quantitative" },
        }),
      ),
    ).toBe(0.8);
  });

  it("prefers fields earlier in the schema as a tie-break", () => {
    const earlier = candidate("point", {});
    earlier.fields = ["group"];
    const later = candidate("point", {});
    later.fields = ["value"];

    expect(fieldOrderScore(PROFILE, earlier)).toBeGreaterThan(
      fieldOrderScore(PROFILE, later),
    );
  });

  it("exposes the combined CompassQL score", () => {
    const score = compassScore(
      PROFILE,
      candidate("point", { x: q, y: { ...q, field: "time" } }),
    );

    expect(score.effectiveness).toBeGreaterThanOrEqual(-1);
    expect(score.aggregation).toBe(1);
    expect(Array.isArray(score.features)).toBe(true);
  });
});
