import type { VegaType } from "../schema/table-schema";
import { DEFAULT_MARK } from "../metamodel/rules";

export type ChannelState = Record<string, unknown> & {
  field?: string;
  type?: VegaType;
  aggregate?: string;
  bin?: boolean | Record<string, unknown>;
  timeUnit?: string;
  scale?: Record<string, unknown>;
  axis?: Record<string, unknown>;
  legend?: Record<string, unknown>;
  header?: Record<string, unknown>;
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
