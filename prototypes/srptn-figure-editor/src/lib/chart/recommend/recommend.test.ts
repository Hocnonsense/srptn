import { describe, expect, it } from "vitest";

import { buildSpec } from "../engine/buildSpec";
import { validateSpec } from "../engine/validate";
import { validateChartState } from "../engine/validateState";
import { inferTableSchema } from "../schema/table-schema";
import {
  createInitialState,
  createLayer,
  type ChartState,
} from "../state/types";
import { applyChartPatch } from "./patch";
import { generateRecommendations } from "./generate";
import type { Recommendation } from "./types";

const TABLE = inferTableSchema(
  Array.from({ length: 40 }, (_, index) => ({
    time: `2026-${String((index % 12) + 1).padStart(2, "0")}-01`,
    value: index + 1,
    size_value: (index * 3) % 10,
    group: index % 2 === 0 ? "a" : "b",
    site: index % 3 === 0 ? "s1" : "s2",
    id: `sample-${index}`,
  })),
);

function state(
  mark: string,
  encoding: ChartState["layers"][number]["encoding"],
): ChartState {
  const chart = createInitialState(mark);
  chart.layers[0].encoding = encoding;
  return chart;
}

function find(
  items: Recommendation[],
  title: string,
): Recommendation | undefined {
  return items.find((item) => item.title === title);
}

describe("next-step recommendations", () => {
  it("recommends adding a quantitative field and a facet", () => {
    const base = state("point", {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
    });
    const items = generateRecommendations(TABLE, base);

    expect(find(items, "Size by size_value")).toBeDefined();
    const facet = find(items, "Facet by group");
    expect(facet).toBeDefined();
    expect(facet?.state.shared.encoding.row).toEqual({
      field: "group",
      type: "nominal",
    });
  });

  it("recommends alternative encodings", () => {
    const base = state("point", {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
      color: { field: "group", type: "nominal" },
    });
    const items = generateRecommendations(TABLE, base);

    expect(find(items, "Flip x and y")).toBeDefined();
    expect(find(items, "Use fill instead of color")).toBeDefined();
  });

  it("recommends summaries and refinements", () => {
    const scatter = state("point", {
      x: { field: "value", type: "quantitative" },
      y: { field: "size_value", type: "quantitative" },
    });
    expect(find(generateRecommendations(TABLE, scatter), "Add linear fit (new layer)")).toBeDefined();

    const comparison = state("point", {
      x: { field: "group", type: "nominal" },
      y: { field: "value", type: "quantitative" },
    });
    expect(
      find(
        generateRecommendations(TABLE, comparison),
        "Show mean value by group",
      ),
    ).toBeDefined();

    const bar = state("bar", {
      x: { field: "group", type: "nominal" },
      y: { field: "value", type: "quantitative", aggregate: "mean" },
    });
    expect(
      find(generateRecommendations(TABLE, bar), "Sort group by value"),
    ).toBeDefined();
  });

  it("considers every layer and can add a new layer", () => {
    const base = state("point", {
      x: { field: "value", type: "quantitative" },
      y: { field: "size_value", type: "quantitative" },
    });
    const line = createLayer("line");
    line.encoding = {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
    };
    base.layers.push(line);

    const items = generateRecommendations(TABLE, base);

    expect(items.some((item) => item.title.startsWith("Layer 1:"))).toBe(
      true,
    );
    expect(items.some((item) => item.title.startsWith("Layer 2:"))).toBe(
      true,
    );
    expect(
      items.some((item) => item.title.includes("Add linear fit (new layer)")),
    ).toBe(true);
  });

  it("keeps recommendation ids stable across runs", () => {
    const base = state("point", {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
      color: { field: "group", type: "nominal" },
    });

    const first = generateRecommendations(TABLE, base);
    const second = generateRecommendations(TABLE, base);

    expect(first.map((item) => item.id)).toEqual(
      second.map((item) => item.id),
    );
  });

  it("does not add row facet when a facet channel already exists", () => {
    const base = state("point", {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
    });
    base.shared.encoding.facet = {
      field: "group",
      type: "nominal",
    };

    const items = generateRecommendations(TABLE, base);

    expect(items.some((item) => item.title.startsWith("Facet by"))).toBe(
      false,
    );
  });

  it("describes mark changes in summaries", () => {
    const base = state("line", {
      x: { field: "group", type: "nominal" },
      y: { field: "value", type: "quantitative" },
    });
    const mean = find(
      generateRecommendations(TABLE, base),
      "Show mean value by group",
    );

    expect(mean?.description).toContain("Switch to bars");
  });

  it("filters discouraged mark/channel combinations", () => {
    const base = state("point", {
      x: { field: "value", type: "quantitative" },
      y: { field: "size_value", type: "quantitative" },
      detail: { field: "site", type: "nominal" },
    });

    const items = generateRecommendations(TABLE, base);

    expect(find(items, "Use rect mark")).toBeUndefined();
    expect(find(items, "Use bar mark")).toBeUndefined();
  });

  it("generates applicable patches and valid states", () => {
    const base = state("point", {
      x: { field: "time", type: "temporal" },
      y: { field: "value", type: "quantitative" },
      color: { field: "group", type: "nominal" },
    });
    const items = generateRecommendations(TABLE, base);
    const seen = new Set<string>();

    for (const item of items) {
      expect(seen.has(JSON.stringify(item.state))).toBe(false);
      seen.add(JSON.stringify(item.state));
      expect(applyChartPatch(base, item.patch)).toEqual(item.state);
      expect(
        validateChartState(item.state).filter(
          (issue) => issue.severity === "error",
        ),
      ).toEqual([]);
      expect(
        validateSpec(
          buildSpec(item.state, { includeData: true, rows: TABLE.rows }),
        ),
      ).toEqual([]);
    }
  });
});
