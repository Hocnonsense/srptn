import type { VegaType } from "../schema/table-schema";
import { VEGA_TYPES } from "../schema/table-schema";
import { enumOf } from "../schema/vl-schema";
import type { Channel, FacetChannel } from "vega-lite/types_unstable/channel.js";

export type { Channel, FacetChannel };

export type SharedChannel = Channel | FacetChannel;

export type Availability = "available" | "warning" | "invalid";

export interface ChannelRule {
  status: Availability;
  reason?: string;
}

const RANGED_MARKS = new Set(["area", "bar", "rect", "rule", "image"]);
const SHAPE_MARKS = new Set(["point", "circle", "square"]);
const ARC_MARKS = new Set(["arc"]);

const ARC_REASON = "Theta/radius channels require an arc mark.";
const RANGED_REASON = "x2/y2 are only available for ranged marks (area/bar/rect/rule).";

export const CHANNEL_SPECS = {
  x: { guide: "axis" },
  y: { guide: "axis" },
  color: { guide: "legend" },
  fill: { guide: "legend" },
  size: { types: ["quantitative", "ordinal", "nominal"], guide: "legend" },
  shape: { types: ["nominal", "ordinal"], marks: { allowed: SHAPE_MARKS, reason: "Shape is only available for point-like marks." }, guide: "legend" },
  text: { marks: { allowed: new Set(["text"]), reason: "The text channel is only available for text marks." } },
  tooltip: {},
  opacity: { types: ["quantitative", "ordinal", "nominal"], guide: "legend" },
  fillOpacity: { types: ["quantitative", "ordinal", "nominal"], guide: "legend" },
  stroke: { guide: "legend" },
  strokeOpacity: { types: ["quantitative", "ordinal", "nominal"], guide: "legend" },
  strokeWidth: { types: ["quantitative", "ordinal", "nominal"], guide: "legend" },
  strokeDash: { types: ["ordinal", "nominal"], guide: "legend" },
  detail: {},
  time: {},
  x2: { marks: { allowed: RANGED_MARKS, reason: RANGED_REASON } },
  y2: { marks: { allowed: RANGED_MARKS, reason: RANGED_REASON } },
  xOffset: {},
  yOffset: {},
  theta: { types: ["quantitative"], marks: { allowed: ARC_MARKS, reason: ARC_REASON }, guide: "legend" },
  theta2: { types: ["quantitative"], marks: { allowed: ARC_MARKS, reason: ARC_REASON } },
  radius: { types: ["quantitative"], marks: { allowed: ARC_MARKS, reason: ARC_REASON }, guide: "legend" },
  radius2: { types: ["quantitative"], marks: { allowed: ARC_MARKS, reason: ARC_REASON } },
  longitude: { types: ["quantitative"] },
  latitude: { types: ["quantitative"] },
  longitude2: { types: ["quantitative"] },
  latitude2: { types: ["quantitative"] },
  angle: { types: ["quantitative"], guide: "legend" },
  href: { types: ["nominal", "ordinal"] },
  url: { types: ["nominal", "ordinal"], marks: { allowed: new Set(["image"]), reason: "The url channel is only available for image marks." } },
  description: { types: ["nominal", "ordinal"] },
  key: { types: ["nominal", "ordinal"] },
  order: { types: ["quantitative", "ordinal"] },
} as const satisfies Record<Channel, ChannelSpec>;

export const FACET_CHANNEL_SPECS = {
  row: { types: ["nominal", "ordinal"] },
  column: { types: ["nominal", "ordinal"] },
  facet: { types: ["nominal", "ordinal"] },
} as const satisfies Record<FacetChannel, ChannelSpec>;

export const CHANNELS = Object.keys(CHANNEL_SPECS) as Channel[];

export const FACET_CHANNELS = new Set(
  Object.keys(FACET_CHANNEL_SPECS) as FacetChannel[],
);

interface ChannelSpec {
  guide?: GuideKind;
  types?: readonly VegaType[];                              // undefined = 全类型
  marks?: { allowed: ReadonlySet<string>; reason: string }; // undefined = 不限 mark
}

export function channelTypes(channel: SharedChannel): readonly VegaType[] {
  if (channel in FACET_CHANNEL_SPECS) {
    const spec = FACET_CHANNEL_SPECS[channel as FacetChannel];
    return spec.types ?? VEGA_TYPES;
  }
  const spec: ChannelSpec = CHANNEL_SPECS[channel as Channel];
  return spec.types ?? VEGA_TYPES;
}

export function markChannelRule(
  mark: string,
  channel: SharedChannel,
): ChannelRule {
  if (channel in FACET_CHANNEL_SPECS) {
    return { status: "available" };
  }
  const spec: ChannelSpec = CHANNEL_SPECS[channel as Channel];
  const rule = spec.marks;
  if (rule && !rule.allowed.has(mark)) {
    return { status: "invalid", reason: rule.reason };
  }
  return { status: "available" };
}

export function fieldStatus(
  mark: string,
  channel: SharedChannel,
  fieldType: VegaType,
): ChannelRule {
  const markRule = markChannelRule(mark, channel);
  if (markRule.status === "invalid") {
    return markRule;
  }
  if (!channelTypes(channel).includes(fieldType)) {
    return {
      status: "invalid",
      reason: `${channel} does not accept ${fieldType} fields.`,
    };
  }
  return { status: "available" };
}

export type GuideKind = "axis" | "legend" | "header" | "none";

export function guideForChannel(channel: SharedChannel): GuideKind {
  if (channel in FACET_CHANNEL_SPECS) {
    return "header";
  }
  const spec = (CHANNEL_SPECS as Record<string, ChannelSpec>)[channel];
  return spec?.guide ?? "none";
}

export const SCALE_TYPES_BY_FIELD_TYPE: Record<VegaType, string[]> = {
  quantitative: ["linear", "log", "pow", "sqrt", "symlog"],
  temporal: ["time", "utc"],
  ordinal: ["band", "point"],
  nominal: ["band", "point"],
};

export function scaleTypes(
  channel: Channel,
  fieldType: VegaType,
): string[] {
  if (channel === "color" || channel === "fill" || channel === "stroke") {
    if (fieldType === "quantitative") {
      return ["linear", "log", "pow", "sqrt", "symlog", "sequential"];
    }
    if (fieldType === "temporal") {
      return ["time", "utc"];
    }
    return ["ordinal"];
  }
  if (channel === "theta" || channel === "radius" || channel === "size") {
    if (fieldType === "quantitative") {
      return ["linear", "sqrt", "pow", "log"];
    }
  }
  return SCALE_TYPES_BY_FIELD_TYPE[fieldType] ?? [];
}

export const CATEGORICAL_SCHEMES = enumOf("#/definitions/Categorical");

export const SEQUENTIAL_SCHEMES = [
  ...enumOf("#/definitions/SequentialSingleHue"),
  ...enumOf("#/definitions/SequentialMultiHue"),
];

export function colorSchemes(fieldType: VegaType): readonly string[] {
  return fieldType === "quantitative" || fieldType === "temporal"
    ? SEQUENTIAL_SCHEMES
    : CATEGORICAL_SCHEMES;
}

export const AGGREGATE_OPS = [
  "count",
  "mean",
  "median",
  "sum",
  "min",
  "max",
] as const;

export const DEFAULT_MARK = "point";
