import type {
  ChartState,
  ChannelState,
  LayerState,
  RawState,
} from "../state/types";
import { VL_SCHEMA_URL } from "../schema/vl-schema";
import {
  collectAggregateOps,
  finalizeTransforms,
} from "./aggregate";
import { toSpecTransforms } from "./transforms";

export interface BuildOptions {
  rows?: Record<string, unknown>[];
  includeData?: boolean;
  schemaUrl?: string;
}

export function buildSpec(
  state: ChartState,
  options: BuildOptions = {},
): Record<string, unknown> {
  const sharedAggregates = collectAggregateOps(state.shared.transform);
  const sharedAggregateNames = new Set(
    sharedAggregates.map((aggregate) => aggregate.name),
  );
  const sharedTransform = toSpecTransforms(
    finalizeTransforms(state.shared.transform, state.shared.encoding),
  );
  const layer = state.layers.map((item) =>
    buildLayer(
      item,
      finalizeTransforms(
        item.transform,
        { ...state.shared.encoding, ...item.encoding },
        sharedAggregateNames,
      ),
    ),
  );
  const sharedEncoding = buildEncoding(state.shared.encoding);
  const schema =
    options.schemaUrl ?? state.schema ?? VL_SCHEMA_URL;
  const spec: Record<string, unknown> = {
    $schema: schema,
    data:
      options.includeData && options.rows
        ? { values: options.rows }
        : { name: "data" },
    layer,
  };
  if (Object.keys(sharedEncoding).length > 0) {
    spec.encoding = sharedEncoding;
  }
  if (sharedTransform.length > 0) {
    spec.transform = sharedTransform;
  }

  if (state.title) {
    spec.title = state.title;
  }
  if (state.width !== undefined) {
    spec.width = state.width;
  }
  if (state.height !== undefined) {
    spec.height = state.height;
  }
  if (state.background) {
    spec.background = state.background;
  }
  if (Object.keys(state.config).length > 0) {
    spec.config = state.config;
  }
  for (const [key, value] of Object.entries(state.extras)) {
    if (!(key in spec)) {
      spec[key] = value;
    }
  }

  const data = spec.data;
  delete spec.data;
  const pruned = prune(spec) as Record<string, unknown>;
  if (data !== undefined) {
    pruned.data = data;
  }
  applyRaw(pruned, state.shared.raw);
  const layers = pruned.layer;
  if (Array.isArray(layers)) {
    state.layers.forEach((layer, index) => {
      const target = layers[index];
      if (target && typeof target === "object" && !Array.isArray(target)) {
        applyRaw(target as Record<string, unknown>, layer.raw);
      }
    });
  }
  return pruned;
}

function buildEncoding(
  source: Record<string, ChannelState>,
): Record<string, unknown> {
  const encoding: Record<string, unknown> = {};
  for (const [channel, channelState] of Object.entries(source)) {
    const fieldDef = pruneChannel(channelState);
    if (fieldDef) {
      encoding[channel] = fieldDef;
    }
  }
  return encoding;
}

function buildLayer(
  layer: LayerState,
  transform: Record<string, unknown>[],
): Record<string, unknown> {
  const encoding = buildEncoding(layer.encoding);
  if (Array.isArray(layer.extras.layer)) {
    // TODO: emit editable nested layers instead of passing raw layer items through.
    const nested: Record<string, unknown> = {};
    if (Object.keys(encoding).length > 0) {
      nested.encoding = encoding;
    }
    if (transform.length > 0) {
      nested.transform = toSpecTransforms(transform);
    }
    for (const [key, value] of Object.entries(layer.extras)) {
      if (!(key in nested)) {
        nested[key] = value;
      }
    }
    return prune(nested) as Record<string, unknown>;
  }

  const mark = layer.markDef
    ? { ...layer.markDef, type: layer.mark }
    : layer.mark;
  const result: Record<string, unknown> = {
    mark,
    encoding,
  };
  if (transform.length > 0) {
    result.transform = toSpecTransforms(transform);
  }
  for (const [key, value] of Object.entries(layer.extras)) {
    if (!(key in result)) {
      result[key] = value;
    }
  }
  return prune(result) as Record<string, unknown>;
}

function applyRaw(
  target: Record<string, unknown>,
  raw: RawState | undefined,
): void {
  if (!raw) {
    return;
  }
  if (raw.encoding && Object.keys(raw.encoding).length > 0) {
    const encoding =
      target.encoding &&
      typeof target.encoding === "object" &&
      !Array.isArray(target.encoding)
        ? (target.encoding as Record<string, unknown>)
        : {};
    target.encoding = { ...encoding, ...raw.encoding };
  }
  if (raw.transforms && raw.transforms.length > 0) {
    const transforms = Array.isArray(target.transform)
      ? target.transform
      : [];
    target.transform = [...transforms, ...raw.transforms];
  }
}

function pruneChannel(
  channelState: ChannelState,
): Record<string, unknown> | undefined {
  const fieldDef = prune(channelState) as Record<string, unknown> | undefined;
  if (!fieldDef) {
    return undefined;
  }
  const hasField = typeof fieldDef.field === "string" && fieldDef.field !== "";
  if (!hasField && fieldDef.aggregate !== "count") {
    return undefined;
  }
  if (hasField && !fieldDef.type) {
    return undefined;
  }
  if (!hasField && fieldDef.aggregate === "count" && !fieldDef.type) {
    fieldDef.type = "quantitative";
  }
  return fieldDef;
}

export function prune(value: unknown): unknown {
  if (Array.isArray(value)) {
    const items = value.map(prune).filter((item) => item !== undefined);
    return items.length > 0 ? items : undefined;
  }
  if (value && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const pruned = prune(item);
      if (pruned !== undefined) {
        result[key] = pruned;
      }
    }
    return Object.keys(result).length > 0 ? result : undefined;
  }
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  return value;
}
