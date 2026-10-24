import type { Aggregate } from "vega-lite/types_unstable/aggregate.js";
import type { Axis } from "vega-lite/types_unstable/axis.js";
import type { Bin } from "vega-lite/types_unstable/bin.js";
import type { ExprRef } from "vega-lite/types_unstable/expr.js";
import type { Header } from "vega-lite/types_unstable/header.js";
import type { Legend } from "vega-lite/types_unstable/legend.js";
import type { Scale } from "vega-lite/types_unstable/scale.js";
import type {
  BinnedTimeUnit,
  TimeUnit,
  TimeUnitParams,
} from "vega-lite/types_unstable/timeunit.js";
import type { SignalRef } from "vega";
import type { VegaType } from "../schema/table-schema";
import { DEFAULT_MARK } from "../metamodel/rules";

export type ChannelState = Record<string, unknown> & {
  field?: string;
  type?: VegaType;
  aggregate?: Aggregate;
  bin?: Bin;
  timeUnit?: TimeUnit | BinnedTimeUnit | TimeUnitParams;
  scale?: Scale;
  axis?: Axis;
  legend?: Legend<ExprRef | SignalRef>;
  header?: Header<ExprRef | SignalRef>;
};

export interface RawState {
  encoding?: Record<string, unknown>;
  transforms?: unknown[];
}

export interface LayerState {
  mark: string;
  markDef?: Record<string, unknown>;
  encoding: Record<string, ChannelState>;
  transform: Record<string, unknown>[];
  raw?: RawState;
  extras: Record<string, unknown>;
}

export type Scope = "shared" | "layer";

export interface ChartState {
  shared: {
    encoding: Record<string, ChannelState>;
    transform: Record<string, unknown>[];
    raw?: RawState;
  };
  layers: LayerState[];
  schema?: string;
  title?: string;
  width?: number;
  height?: number;
  background?: string;
  config: Record<string, unknown>;
  extras: Record<string, unknown>;
}

export function createLayer(mark = DEFAULT_MARK): LayerState {
  return {
    mark,
    encoding: {},
    transform: [],
    extras: {},
  };
}

export function createInitialState(mark = DEFAULT_MARK): ChartState {
  return {
    shared: { encoding: {}, transform: [] },
    layers: [createLayer(mark)],
    title: "",
    config: {},
    extras: {},
  };
}

export function activeLayer(state: ChartState, index: number): LayerState {
  return state.layers[index] ?? state.layers[0] ?? createLayer();
}

export function clampLayerIndex(state: ChartState, index: number): number {
  return Math.max(0, Math.min(index, state.layers.length - 1));
}
