import type { ChartState, ChannelState, LayerState } from "../state/types";
import { createInitialState, createLayer } from "../state/types";
import { withTransformMetadata } from "./transforms";

const ROOT_KEYS = new Set([
  "$schema",
  "data",
  "mark",
  "encoding",
  "transform",
  "title",
  "width",
  "height",
  "background",
  "config",
  "facet",
  "layer",
  "spec",
]);

const LAYER_KEYS = new Set(["mark", "encoding", "transform"]);

export function parseSpec(spec: Record<string, unknown>): ChartState {
  const state = createInitialState();
  const root = { ...spec };
  const wrappedSpec =
    isRecord(root.spec) && !Array.isArray(root.layer)
      ? root.spec
      : undefined;
  const container = wrappedSpec ?? root;

  if (Array.isArray(container.layer)) {
    const sharedEncoding = copyEncoding(container.encoding);
    state.shared.encoding = sharedEncoding.encoding;
    if (sharedEncoding.raw) {
      state.shared.raw = { encoding: sharedEncoding.raw };
    }
    const sharedTransforms = splitTransforms(container.transform);
    state.shared.transform = sharedTransforms.transforms;
    if (sharedTransforms.raw) {
      state.shared.raw = {
        ...state.shared.raw,
        transforms: sharedTransforms.raw,
      };
    }
    state.layers = container.layer
      .filter(isRecord)
      .map((item) => parseLayer(item, true));
  } else {
    state.layers = [parseLayer(container, wrappedSpec !== undefined)];
  }

  if (typeof root.$schema === "string") {
    state.schema = root.$schema;
  }
  if (typeof root.title === "string") {
    state.title = root.title;
  } else if (root.title !== undefined) {
    state.extras.title = root.title;
  }
  if (typeof root.width === "number") {
    state.width = root.width;
  } else if (root.width !== undefined) {
    state.extras.width = root.width;
  }
  if (typeof root.height === "number") {
    state.height = root.height;
  } else if (root.height !== undefined) {
    state.extras.height = root.height;
  }
  if (typeof root.background === "string") {
    state.background = root.background;
  } else if (root.background !== undefined) {
    state.extras.background = root.background;
  }
  if (isRecord(root.config)) {
    state.config = { ...root.config };
  }
  if (isRecord(root.facet)) {
    const facet = root.facet;
    if (isRecord(facet.row)) {
      state.shared.encoding.row = { ...facet.row } as ChannelState;
    }
    if (isRecord(facet.column)) {
      state.shared.encoding.column = { ...facet.column } as ChannelState;
    }
    if (typeof facet.field === "string" && typeof facet.type === "string") {
      state.shared.encoding.facet = { ...facet } as ChannelState;
    }
  }

  for (const [key, value] of Object.entries(root)) {
    if (!ROOT_KEYS.has(key)) {
      state.extras[key] = value;
    }
  }

  return state;
}

function parseLayer(item: Record<string, unknown>, includeExtras: boolean): LayerState {
  const layer = createLayer();
  if (typeof item.mark === "string") {
    layer.mark = item.mark;
  } else if (isRecord(item.mark) && typeof item.mark.type === "string") {
    layer.mark = item.mark.type;
    layer.markDef = { ...item.mark };
  }

  const encoding = copyEncoding(item.encoding);
  layer.encoding = encoding.encoding;
  if (encoding.raw) {
    layer.raw = { encoding: encoding.raw };
  }
  const transforms = splitTransforms(item.transform);
  layer.transform = transforms.transforms;
  if (transforms.raw) {
    layer.raw = { ...layer.raw, transforms: transforms.raw };
  }

  if (includeExtras) {
    // TODO: parse nested `layer` items into editable sub-layers instead of raw extras.
    for (const [key, value] of Object.entries(item)) {
      if (!LAYER_KEYS.has(key)) {
        layer.extras[key] = value;
      }
    }
  }

  return layer;
}

function copyEncoding(value: unknown): {
  encoding: Record<string, ChannelState>;
  raw?: Record<string, unknown>;
} {
  const encoding: Record<string, ChannelState> = {};
  const raw: Record<string, unknown> = {};
  if (!isRecord(value)) {
    return { encoding };
  }
  for (const [channel, channelDef] of Object.entries(value)) {
    if (isRecord(channelDef)) {
      encoding[channel] = { ...channelDef } as ChannelState;
    } else {
      raw[channel] = channelDef;
    }
  }
  return Object.keys(raw).length > 0
    ? { encoding, raw }
    : { encoding };
}

function splitTransforms(value: unknown): {
  transforms: Record<string, unknown>[];
  raw?: unknown[];
} {
  const transforms: Record<string, unknown>[] = [];
  const raw: unknown[] = [];
  if (Array.isArray(value)) {
    for (const item of value) {
      if (isRecord(item)) {
        transforms.push(withTransformMetadata(item));
      } else {
        raw.push(item);
      }
    }
  }
  return raw.length > 0 ? { transforms, raw } : { transforms };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
