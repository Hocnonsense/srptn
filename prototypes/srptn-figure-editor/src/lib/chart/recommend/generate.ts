import { validateChartState } from "../engine/validateState";
import { fieldStatus } from "../metamodel/rules";
import type { SharedChannel } from "../metamodel/rules";
import type { TableSchema } from "../schema/table-schema";
import {
  createLayer,
  type ChartState,
  type LayerState,
} from "../state/types";
import {
  hasDerive,
  hasDeriveKind,
} from "../engine/channelFn";
import { isDimensionState } from "./compassql";
import { diffChartState } from "./patch";
import {
  createRecommendationProfile,
  fieldUsable,
  pairSignificanceOf,
  significanceOf,
  type FieldProfile,
  type RecommendationProfile,
} from "./profile";
import { scoreCandidate } from "./score";
import type { Candidate } from "./types";
import type {
  Recommendation,
  RecommendationCategory,
} from "./types";

export function generateRecommendations(
  table: TableSchema,
  state: ChartState,
): Recommendation[] {
  const profile = createRecommendationProfile(table);
  if (state.layers.length === 0) {
    return [];
  }
  const seen = new Set<string>();
  const recommendations: Recommendation[] = [];

  const addRecommendation = (
    category: RecommendationCategory,
    title: string,
    description: string,
    next: ChartState,
    heuristic: number,
    current: ReturnType<typeof stateScore>,
    scoreNext: () => ReturnType<typeof stateScore>,
  ) => {
    const key = stableStringify(next);
    if (seen.has(key)) {
      return;
    }
    const errors = validateChartState(next).filter(
      (issue) => issue.severity === "error",
    );
    if (errors.length > 0) {
      return;
    }
    const delta = scoreNext().total - current.total;
    const score = clamp01(
      0.55 * heuristic + 0.45 * ((delta + 1) / 2),
    );
    seen.add(key);
    recommendations.push({
      id: `${category}:${hashKey(key)}`,
      category,
      title,
      description,
      state: next,
      patch: diffChartState(state, next),
      score,
    });
  };

  for (let index = 0; index < state.layers.length; index += 1) {
    const current = stateScore(profile, state, index);
    const add: AddRecommendation = (
      category,
      title,
      description,
      next,
      heuristic,
    ) => {
      addRecommendation(
        category,
        state.layers.length > 1 ? `Layer ${index + 1}: ${title}` : title,
        description,
        next,
        heuristic,
        current,
        () => stateScore(profile, next, index),
      );
    };
    addFieldRecommendations(profile, state, index, add);
    alternativeRecommendations(state, index, add);
    summaryRecommendations(profile, state, index, add);
    refinementRecommendations(profile, state, index, add);
    replacementRecommendations(profile, state, index, add);
  }

  const sharedCurrent = stateScore(profile, state, 0);
  const addShared: AddRecommendation = (
    category,
    title,
    description,
    next,
    heuristic,
  ) => {
    addRecommendation(
      category,
      title,
      description,
      next,
      heuristic,
      sharedCurrent,
      () => stateScore(profile, next, 0),
    );
  };
  facetRecommendations(profile, state, addShared);

  const priority: Record<RecommendationCategory, number> = {
    quantitative: 0,
    categorical: 1,
    temporal: 2,
    encoding: 3,
    summary: 4,
    refinement: 5,
    replacement: 6,
  };
  return recommendations.sort(
    (left, right) =>
      priority[left.category] - priority[right.category] ||
      right.score - left.score,
  );
}

type AddRecommendation = (
  category: RecommendationCategory,
  title: string,
  description: string,
  next: ChartState,
  heuristic: number,
) => void;

function addFieldRecommendations(
  profile: RecommendationProfile,
  state: ChartState,
  index: number,
  add: AddRecommendation,
): void {
  const layer = activeLayer(state, index);
  const used = new Set(
    [
      ...Object.values(layer.encoding),
      ...Object.values(state.shared.encoding),
    ]
      .map((channel) => channel.field)
      .filter((field): field is string => typeof field === "string"),
  );
  const fields = profile.fields.filter(
    (field) => fieldUsable(field) && !used.has(field.name),
  );
  const specs: {
    channel: SharedChannel;
    roles: FieldProfile["role"][];
    min?: number;
    max?: number;
    marks?: string[];
    title: (field: FieldProfile) => string;
    description: (field: FieldProfile) => string;
    weight: number;
  }[] = [
      {
        channel: "size",
        roles: ["measure"],
        marks: ["point", "circle", "square", "line", "area"],
        title: (field) => `Size by ${field.name}`,
        description: (field) =>
          `Add ${field.name} as size to expose an extra quantitative dimension.`,
        weight: 1,
      },
      {
        channel: "color",
        roles: ["dimension"],
        min: 2,
        max: 12,
        title: (field) => `Color by ${field.name}`,
        description: (field) =>
          `Split marks by ${field.name} using color.`,
        weight: 0.95,
      },
      {
        channel: "shape",
        roles: ["dimension"],
        min: 2,
        max: 6,
        marks: ["point", "circle", "square"],
        title: (field) => `Shape by ${field.name}`,
        description: (field) =>
          `Use shape to distinguish ${field.name} groups.`,
        weight: 0.65,
      },
      {
        channel: "detail",
        roles: ["dimension"],
        min: 2,
        max: 12,
        title: (field) => `Split by ${field.name}`,
        description: (field) =>
          `Separate series by ${field.name} without adding a visible channel.`,
        weight: 0.55,
      },
    ];

  for (const spec of specs) {
    if (spec.channel in layer.encoding) {
      continue;
    }
    if (
      spec.marks &&
      !spec.marks.includes(layer.mark) &&
      !(layer.mark === "circle" || layer.mark === "square")
    ) {
      continue;
    }
    const field = fields
      .filter(
        (candidate) =>
          spec.roles.includes(candidate.role) &&
          (spec.min === undefined || candidate.distinctCount >= spec.min) &&
          (spec.max === undefined || candidate.distinctCount <= spec.max) &&
          fieldStatus(layer.mark, spec.channel, candidate.type).status !== "invalid",
      )
      .sort((left, right) => fieldScore(profile, right) - fieldScore(profile, left))[0];
    if (!field) {
      continue;
    }

    const next = cloneState(state);
    activeLayer(next, index).encoding[spec.channel] = {
      field: field.name,
      type: field.type,
    };
    add(
      field.role === "measure"
        ? "quantitative"
        : field.role === "time"
          ? "temporal"
          : "categorical",
      spec.title(field),
      spec.description(field),
      next,
      fieldScore(profile, field) * spec.weight,
    );
  }
}

function replacementRecommendations(
  profile: RecommendationProfile,
  state: ChartState,
  index: number,
  add: AddRecommendation,
): void {
  const layer = activeLayer(state, index);
  const used = new Set(
    [
      ...Object.values(state.shared.encoding),
      ...Object.values(layer.encoding),
    ]
      .map((channel) => channel.field)
      .filter((field): field is string => typeof field === "string"),
  );
  const available = profile.fields.filter(
    (field) => fieldUsable(field) && !used.has(field.name),
  );
  const replacementChannels: SharedChannel[] = [
    "x",
    "y",
    "color",
    "size",
    "shape",
    "detail",
  ];

  const alternatives = (channel: SharedChannel): FieldProfile[] => {
    const current = layer.encoding[channel];
    return available
      .filter(
        (field) =>
          sameRole(current?.type, field.type) &&
          fieldStatus(layer.mark, channel, field.type).status !== "invalid",
      )
      .sort(
        (left, right) =>
          fieldScore(profile, right) - fieldScore(profile, left),
      )
      .slice(0, 2);
  };

  for (const channel of replacementChannels) {
    const current = layer.encoding[channel];
    if (!current?.field) {
      continue;
    }
    for (const field of alternatives(channel)) {
      const next = cloneState(state);
      activeLayer(next, index).encoding[channel] = {
        ...current,
        field: field.name,
        type: field.type,
      };
      add(
        "replacement",
        `Replace ${channel}: ${current.field} → ${field.name}`,
        `Try ${field.name} on ${channel} instead of ${current.field}.`,
        next,
        fieldScore(profile, field) * 0.45,
      );
    }
  }

  const pairs: [SharedChannel, SharedChannel][] = [
    ["x", "color"],
    ["y", "color"],
    ["x", "y"],
  ];
  for (const [left, right] of pairs) {
    const leftState = layer.encoding[left];
    const rightState = layer.encoding[right];
    if (!leftState?.field || !rightState?.field) {
      continue;
    }
    const leftField = alternatives(left)[0];
    const rightField = alternatives(right).find(
      (field) => field.name !== leftField?.name,
    );
    if (!leftField || !rightField) {
      continue;
    }
    const next = cloneState(state);
    const target = activeLayer(next, index);
    target.encoding[left] = {
      ...leftState,
      field: leftField.name,
      type: leftField.type,
    };
    target.encoding[right] = {
      ...rightState,
      field: rightField.name,
      type: rightField.type,
    };
    add(
      "replacement",
      `Replace ${left} and ${right}: ${leftState.field}/${rightState.field} → ${leftField.name}/${rightField.name}`,
      `Try ${leftField.name} on ${left} and ${rightField.name} on ${right}.`,
      next,
      ((fieldScore(profile, leftField) + fieldScore(profile, rightField)) / 2) * 0.4,
    );
  }
}

function facetRecommendations(
  profile: RecommendationProfile,
  state: ChartState,
  add: AddRecommendation,
): void {
  if (
    state.shared.encoding.row ||
    state.shared.encoding.column ||
    state.shared.encoding.facet
  ) {
    return;
  }
  const used = new Set(
    [
      ...Object.values(state.shared.encoding),
      ...state.layers.flatMap((layer) => Object.values(layer.encoding)),
    ]
      .map((channel) => channel.field)
      .filter((field): field is string => typeof field === "string"),
  );
  const field = profile.fields
    .filter(
      (candidate) =>
        fieldUsable(candidate) &&
        !used.has(candidate.name) &&
        (candidate.cardinality === "binary" ||
          (candidate.distinctCount >= 3 && candidate.distinctCount <= 6)),
    )
    .sort((left, right) => fieldScore(profile, right) - fieldScore(profile, left))[0];
  if (!field) {
    return;
  }
  const next = cloneState(state);
  next.shared.encoding.row = {
    field: field.name,
    type: field.type,
  };
  add(
    "categorical",
    `Facet by ${field.name}`,
    `Create one panel per ${field.name} group.`,
    next,
    fieldScore(profile, field) * 0.8,
  );
}

function alternativeRecommendations(
  state: ChartState,
  index: number,
  add: AddRecommendation,
): void {
  const layer = activeLayer(state, index);
  const { x, y, color, fill } = layer.encoding;

  if (x && y) {
    const next = cloneState(state);
    const target = activeLayer(next, index);
    target.encoding.x = y;
    target.encoding.y = x;
    if (
      fieldStatus(layer.mark, "x", y.type ?? "nominal").status !== "invalid" &&
      fieldStatus(layer.mark, "y", x.type ?? "nominal").status !== "invalid"
    ) {
      add(
        "encoding",
        "Flip x and y",
        "Swap the two positional channels.",
        next,
        0.55,
      );
    }
  }

  if (color && !fill) {
    if (fieldStatus(layer.mark, "fill", color.type ?? "nominal").status !== "invalid") {
      const next = cloneState(state);
      const target = activeLayer(next, index);
      delete target.encoding.color;
      target.encoding.fill = color;
      add(
        "encoding",
        "Use fill instead of color",
        "Move the color encoding to fill.",
        next,
        0.55,
      );
    }
  }

  const marks = ["point", "line", "area", "bar", "tick", "rect"];
  const discouraged: Partial<Record<string, readonly SharedChannel[]>> = {
    bar: ["detail", "size"],
    tick: ["detail", "size"],
    rect: ["detail"],
  };
  for (const mark of marks) {
    if (mark === layer.mark) {
      continue;
    }
    const next = cloneState(state);
    activeLayer(next, index).mark = mark;
    const target = activeLayer(next, index);
    const blocked = discouraged[mark] ?? [];
    const valid = Object.entries(target.encoding).every(
      ([channel, channelState]) =>
        !blocked.includes(channel as SharedChannel) &&
        fieldStatus(
          mark,
          channel as SharedChannel,
          channelState.type ?? "nominal",
        ).status !== "invalid",
    );
    if (valid) {
      add(
        "encoding",
        `Use ${mark} mark`,
        `Switch the mark type to ${mark}.`,
        next,
        0.5,
      );
    }
  }

}

function summaryRecommendations(
  profile: RecommendationProfile,
  state: ChartState,
  index: number,
  add: AddRecommendation,
): void {
  const layer = activeLayer(state, index);
  const { x, y } = layer.encoding;
  if (!x) {
    return;
  }
  const xField = fieldOf(profile, x);
  const dimension = isDimensionState(x, xField);

  if (dimension && y && isRawMeasure(y)) {
    const mean = cloneState(state);
    const target = activeLayer(mean, index);
    target.mark = "bar";
    target.encoding.y = {
      ...y,
      aggregate: "mean",
    };
    add(
      "summary",
      `Show mean ${y.field} by ${x.field}`,
      layer.mark === "bar"
        ? `Aggregate ${y.field} across ${x.field}.`
        : `Switch to bars and aggregate ${y.field} across ${x.field}.`,
      mean,
      0.72,
    );

    const count = cloneState(state);
    const countTarget = activeLayer(count, index);
    countTarget.mark = "bar";
    countTarget.encoding.y = {
      aggregate: "count",
      type: "quantitative",
    };
    add(
      "summary",
      `Count records by ${x.field}`,
      layer.mark === "bar"
        ? `Show how many rows fall into each ${x.field} group.`
        : `Switch to bars and count rows per ${x.field}.`,
      count,
      0.55,
    );
  }

  if (y && typeof y.aggregate === "string" && y.aggregate !== "count") {
    for (const op of ["mean", "sum", "median", "min", "max"] as const) {
      if (op === y.aggregate) {
        continue;
      }
      const next = cloneState(state);
      activeLayer(next, index).encoding.y = {
        ...y,
        aggregate: op,
      };
      add(
        "summary",
        `Use ${op} of ${y.field}`,
        `Change the aggregate for ${y.field} from ${y.aggregate} to ${op}.`,
        next,
        0.5,
      );
    }
  }

  if (
    x.type === "temporal" &&
    !hasDeriveKind(x, "timeUnit") &&
    (xField?.distinctCount ?? 0) > 8
  ) {
    const next = cloneState(state);
    activeLayer(next, index).encoding.x = {
      ...x,
      timeUnit: "yearmonth",
    };
    add(
      "summary",
      `Group ${x.field} by month`,
      `Reduce ${x.field} to monthly values to make the trend readable.`,
      next,
      0.6,
    );
  }

  if (
    x.type === "quantitative" &&
    !hasDeriveKind(x, "bin") &&
    (xField?.distinctCount ?? 0) > 20 &&
    y &&
    (y.aggregate || y.type === "quantitative")
  ) {
    const next = cloneState(state);
    activeLayer(next, index).encoding.x = {
      ...x,
      bin: true,
    };
    add(
      "summary",
      `Bin ${x.field}`,
      `Group ${x.field} into bins.`,
      next,
      0.5,
    );
  }
}

function refinementRecommendations(
  profile: RecommendationProfile,
  state: ChartState,
  index: number,
  add: AddRecommendation,
): void {
  const layer = activeLayer(state, index);
  const { x, y } = layer.encoding;
  if (!x || !y || !x.field || !y.field) {
    return;
  }
  const pair = pairSignificanceOf(profile, x.field, y.field);

  if (
    (layer.mark === "point" || layer.mark === "line") &&
    (x.type === "quantitative" || x.type === "temporal") &&
    y.type === "quantitative" &&
    !y.aggregate &&
    !layer.encoding.color &&
    !layer.encoding.detail &&
    !layer.encoding.shape &&
    !state.layers.some((item) =>
      item.transform.some((transform) => "regression" in transform),
    )
  ) {
    const regression = createLayer("line");
    regression.encoding.x = { ...x };
    regression.encoding.y = { ...y };
    regression.transform = [
      {
        regression: y.field,
        on: x.field,
        method: "linear",
      },
    ];
    const next = cloneState(state);
    next.layers.push(regression);
    add(
      "refinement",
      "Add linear fit (new layer)",
      `Add a new layer with a linear regression for ${y.field} against ${x.field}.`,
      next,
      Math.max(0.35, pair),
    );
  }

  if (layer.mark === "line" && layer.markDef?.point !== true) {
    const next = cloneState(state);
    const target = activeLayer(next, index);
    target.markDef = { ...(target.markDef ?? {}), point: true };
    add(
      "refinement",
      "Show points on the line",
      "Reveal the underlying observations.",
      next,
      0.5,
    );
  }

  if (
    (x.type === "nominal" || x.type === "ordinal") &&
    y.field &&
    (y.aggregate || layer.mark === "bar")
  ) {
    const next = cloneState(state);
    activeLayer(next, index).encoding.x = {
      ...x,
      sort: {
        field: y.field,
        op: y.aggregate ?? "mean",
        order: "descending",
      },
    };
    add(
      "refinement",
      `Sort ${x.field} by ${y.field}`,
      `Order ${x.field} categories by ${y.field}.`,
      next,
      0.55,
    );
  }

  const yColumn =
    typeof y.field === "string"
      ? profile.table.columns.find((column) => column.name === y.field)
      : undefined;
  if (
    y.type === "quantitative" &&
    typeof yColumn?.minimum === "number" &&
    typeof yColumn.maximum === "number" &&
    yColumn.minimum > 0 &&
    yColumn.maximum / yColumn.minimum > 100 &&
    y.scale?.type !== "log"
  ) {
    const next = cloneState(state);
    activeLayer(next, index).encoding.y = {
      ...y,
      scale: { ...(y.scale ?? {}), type: "log" },
    };
    add(
      "refinement",
      `Use log scale for ${y.field}`,
      `The range of ${y.field} spans more than two orders of magnitude.`,
      next,
      0.45,
    );
  }
}

function activeLayer(state: ChartState, index: number): LayerState {
  return state.layers[index] ?? state.layers[0];
}

function cloneState(state: ChartState): ChartState {
  return structuredClone(state);
}

function fieldOf(
  profile: RecommendationProfile,
  state: { field?: string },
): FieldProfile | undefined {
  return typeof state.field === "string"
    ? profile.byName.get(state.field)
    : undefined;
}

function fieldScore(
  profile: RecommendationProfile,
  field: FieldProfile,
): number {
  const significance = significanceOf(profile, field.name);
  const cardinality =
    field.distinctCount <= 8
      ? 1
      : field.distinctCount <= 20
        ? 0.7
        : 0.3;
  return significance * cardinality;
}

function isRawMeasure(state: LayerState["encoding"][string]): boolean {
  return (
    state.type === "quantitative" &&
    !state.aggregate &&
    !hasDerive(state)
  );
}

function stateScore(
  profile: RecommendationProfile,
  state: ChartState,
  index: number,
) {
  const layer = activeLayer(state, index);
  const encoding = { ...state.shared.encoding, ...layer.encoding };
  const fields = Array.from(
    new Set(
      Object.values(encoding)
        .map((channel) => channel.field)
        .filter((field): field is string => typeof field === "string"),
    ),
  );
  const candidate: Candidate = {
    state: {
      ...state,
      shared: { ...state.shared, encoding: {} },
      layers: [{ ...layer, encoding }],
    },
    fields,
    channels: {
      x: encoding.x?.field,
      y: encoding.y?.field,
      color: encoding.color?.field,
    },
    mark: layer.mark,
  };
  return scoreCandidate(profile, candidate);
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(
        ([key, item]) =>
          `${JSON.stringify(key)}:${stableStringify(item)}`,
      );
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

function hashKey(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function sameRole(
  current: LayerState["encoding"][string]["type"],
  next: FieldProfile["type"],
): boolean {
  if (current === "quantitative") {
    return next === "quantitative";
  }
  if (current === "temporal") {
    return next === "temporal";
  }
  return next === "nominal" || next === "ordinal";
}
