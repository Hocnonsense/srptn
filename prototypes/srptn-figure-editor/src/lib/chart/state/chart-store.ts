import { createContext, useContext } from "react";
import { useStore } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

import { DEFAULT_MARK } from "../metamodel/rules";
import type { TableSchema } from "../schema/table-schema";
import { buildSpec } from "../engine/buildSpec";
import {
  aggregateIssues,
  collectAggregateOps,
  upsertAggregate,
} from "../engine/aggregate";
import { derivedFields, fieldIssues } from "../engine/fields";
import { resolveOptions } from "../engine/options";
import { renameFieldInState } from "../engine/rename";
import type { ValidationIssue } from "../engine/validate";
import { validateSpec } from "../engine/validate";
import { validateChartState } from "../engine/validateState";
import type { ChartState, LayerState, Scope } from "./types";
import { activeLayer, createInitialState, createLayer } from "./types";

function updateLayer(
  state: ChartState,
  index: number,
  update: (layer: LayerState) => LayerState,
): ChartState {
  const layers = state.layers.map((layer, layerIndex) =>
    layerIndex === index ? update(layer) : layer,
  );
  return { ...state, layers };
}

export interface ChartStore {
  state: ChartState;
  table: TableSchema;
  activeLayerIndex: number;
  setTable(table: TableSchema): void;
  setMark(mark: string): void;
  setActiveLayer(index: number): void;
  addLayer(mark?: string): void;
  removeLayer(index?: number): void;
  replaceState(state: ChartState): void;
  patchState(patch: Partial<ChartState>): void;
  setField(channel: string, field: string | undefined, scope?: Scope): void;
  addAggregate(scope?: Scope): void;
  renameField(oldName: string, newName: string, scope?: Scope): void;
  setChannel(channel: string, patch: Record<string, unknown>, scope?: Scope): void;
  removeChannel(channel: string, scope?: Scope): void;
  addTransform(transform: Record<string, unknown>, scope?: Scope): void;
  updateTransform(index: number, transform: Record<string, unknown>, scope?: Scope): void;
  removeTransform(index: number, scope?: Scope): void;
  reset(): void;

  spec(options?: {
    includeData?: boolean;
    rows?: Record<string, unknown>[];
  }): Record<string, unknown>;
  issues(options?: { forSave?: boolean }): ValidationIssue[];
  options(channel: string, scope?: Scope): ReturnType<typeof resolveOptions>;
}

export function createChartStore(): StoreApi<ChartStore> {
  return createStore<ChartStore>((set, get) => ({
    state: createInitialState(),
    table: { columns: [], rows: [] },
    activeLayerIndex: 0,

    setTable(table) {
      set({ table });
    },

    setMark(mark) {
      set(({ state, activeLayerIndex }) => ({
        state: updateLayer(state, activeLayerIndex, (layer) => ({
          ...layer,
          mark,
          markDef: undefined,
        })),
      }));
    },

    setActiveLayer(index) {
      set(({ state }) => ({
        activeLayerIndex: Math.max(0, Math.min(index, state.layers.length - 1)),
      }));
    },

    addLayer(mark = DEFAULT_MARK) {
      set(({ state, activeLayerIndex }) => {
        const layers = [...state.layers, createLayer(mark)];
        return { state: { ...state, layers }, activeLayerIndex: layers.length - 1 };
      });
    },

    removeLayer(index = get().activeLayerIndex) {
      set(({ state }) => {
        if (state.layers.length <= 1) {
          return {};
        }
        const layers = state.layers.filter((_, item) => item !== index);
        const activeLayerIndex = Math.max(0, Math.min(index, layers.length - 1));
        return { state: { ...state, layers }, activeLayerIndex };
      });
    },

    replaceState(state) {
      set({ state, activeLayerIndex: 0 });
    },

    patchState(patch) {
      set((current) => ({ state: { ...current.state, ...patch } }));
    },

    setField(channel, field, scope = "layer") {
      const { table, state, activeLayerIndex } = get();
      if (!field) {
        get().removeChannel(channel, scope);
        return;
      }
      const column = table.columns.find((item) => item.name === field);
      set({
        state: updateChannel(
          state,
          activeLayerIndex,
          scope,
          channel,
          (current) => ({
            ...current,
            field,
            type: column?.type ?? current.type ?? "nominal",
          }),
        ),
      });
    },

    addAggregate(scope = "layer") {
      const { state, table, activeLayerIndex } = get();
      const layer = activeLayer(state, activeLayerIndex);
      const transforms =
        scope === "shared" ? state.shared.transform : layer.transform;
      const existing = collectAggregateOps(transforms);

      const orderedColumns = [
        ...table.columns.filter((item) => item.type === "quantitative"),
        ...table.columns.filter((item) => item.type !== "quantitative"),
      ];
      const candidate = orderedColumns
        .flatMap((column) =>
          (column.type === "quantitative"
            ? ["mean", "sum", "median", "min", "max"]
            : ["min", "max"]
          ).map((op) => ({ op, field: column.name })),
        )
        .find(
          (item) =>
            !existing.some(
              (current) =>
                current.op === item.op && current.field === item.field,
            ),
        );
      let op = candidate?.op;
      let field = candidate?.field;
      if (!op && !existing.some((item) => item.op === "count")) {
        op = "count";
        field = undefined;
      }
      if (!op) {
        return;
      }

      const result = upsertAggregate(transforms, op, field);

      if (scope === "shared") {
        set({
          state: {
            ...state,
            shared: { ...state.shared, transform: result.transforms },
          },
          });
        return;
      }

      set({
        state: updateLayer(state, activeLayerIndex, (item) => ({
          ...item,
          transform: result.transforms,
        })),
      });
    },

    renameField(oldName, newName, scope = "layer") {
      if (!oldName || !newName || oldName === newName) {
        return;
      }
      set(({ state, activeLayerIndex }) => ({
        state: renameFieldInState(
          state,
          activeLayerIndex,
          scope,
          oldName,
          newName,
        ),
      }));
    },

    setChannel(channel, patch, scope = "layer") {
      set(({ state, activeLayerIndex }) => ({
        state: updateChannel(
          state,
          activeLayerIndex,
          scope,
          channel,
          (current) => ({ ...current, ...patch }),
        ),
      }));
    },

    removeChannel(channel, scope = "layer") {
      set(({ state, activeLayerIndex }) => ({
        state: updateChannel(
          state,
          activeLayerIndex,
          scope,
          channel,
          () => undefined,
        ),
      }));
    },

    addTransform(transform, scope = "layer") {
      set(({ state, activeLayerIndex }) => ({
        state: updateTransformList(
          state,
          activeLayerIndex,
          scope,
          (items) => [...items, transform],
        ),
      }));
    },

    updateTransform(index, transform, scope = "layer") {
      set(({ state, activeLayerIndex }) => ({
        state: updateTransformList(
          state,
          activeLayerIndex,
          scope,
          (items) =>
            items.map((item, itemIndex) =>
              itemIndex === index ? transform : item,
            ),
        ),
      }));
    },

    removeTransform(index, scope = "layer") {
      set(({ state, activeLayerIndex }) => ({
        state: updateTransformList(
          state,
          activeLayerIndex,
          scope,
          (items) => items.filter((_, itemIndex) => itemIndex !== index),
        ),
      }));
    },

    reset() {
      set({ state: createInitialState(), activeLayerIndex: 0 });
    },

    spec(options = {}) {
      return buildSpec(get().state, options);
    },

    issues(options = {}) {
      const { state, table } = get();
      const baseNames = table.columns.map((column) => column.name);
      const sharedAggregates = collectAggregateOps(state.shared.transform);
      const sharedFields = derivedFields(baseNames, state.shared.transform);
      const sharedAggregateNames = sharedAggregates.map((field) => field.name);
      const sharedNames = [
        ...baseNames,
        ...sharedFields.map((field) => field.name),
        ...sharedAggregateNames,
      ];
      const fieldProblems = [
        ...fieldIssues(
          [...baseNames, ...sharedAggregateNames],
          state.shared.transform,
          "/shared",
        ),
        ...state.layers.flatMap((layer, index) => {
          const layerAggregates = collectAggregateOps(layer.transform);
          return fieldIssues(
            [
              ...sharedNames,
              ...layerAggregates.map((field) => field.name),
            ],
            layer.transform,
            `/layers/${index}`,
          );
        }),
      ];
      const aggregateProblems = [
        ...aggregateIssues(
          [
            ...baseNames,
            ...sharedFields.map((field) => field.name),
          ],
          state.shared.transform,
          "/shared",
        ),
        ...state.layers.flatMap((layer, index) => {
          const layerDerived = derivedFields(
            sharedNames,
            layer.transform,
          );
          return aggregateIssues(
            [
              ...sharedNames,
              ...layerDerived.map((field) => field.name),
            ],
            layer.transform,
            `/layers/${index}`,
          );
        }),
      ];
      return [
        ...validateChartState(state),
        ...fieldProblems,
        ...aggregateProblems,
        ...validateSpec(get().spec({ includeData: true }), options),
      ];
    },

    options(channel, scope = "layer") {
      const { state, table, activeLayerIndex } = get();
      return resolveOptions({
        channel,
        table,
        state,
        layerIndex: activeLayerIndex,
        layer: activeLayer(state, activeLayerIndex),
        scope,
      });
    },
  }));
}

export const ChartStoreContext = createContext<StoreApi<ChartStore> | null>(null);

function useChartStoreApi(): StoreApi<ChartStore> {
  const store = useContext(ChartStoreContext);
  if (!store) {
    throw new Error("Chart store context is missing");
  }
  return store;
}

export function useChartStore<T>(selector: (s: ChartStore) => T): T {
  return useStore(useChartStoreApi(), selector);
}

function updateChannel(
  state: ChartState,
  layerIndex: number,
  scope: Scope,
  channel: string,
  update: (current: Record<string, unknown>) => Record<string, unknown> | undefined,
): ChartState {
  if (scope === "shared") {
    const current = state.shared.encoding[channel] ?? {};
    const next = update(current);
    const encoding = { ...state.shared.encoding };
    if (next === undefined) {
      delete encoding[channel];
    } else {
      encoding[channel] = next;
    }
    return { ...state, shared: { ...state.shared, encoding } };
  }
  return updateLayer(state, layerIndex, (layer) => {
    const current = layer.encoding[channel] ?? {};
    const next = update(current);
    const encoding = { ...layer.encoding };
    if (next === undefined) {
      delete encoding[channel];
    } else {
      encoding[channel] = next;
    }
    return { ...layer, encoding };
  });
}

function updateTransformList(
  state: ChartState,
  layerIndex: number,
  scope: Scope,
  update: (
    items: Record<string, unknown>[],
  ) => Record<string, unknown>[],
): ChartState {
  if (scope === "shared") {
    return {
      ...state,
      shared: {
        ...state.shared,
        transform: update(state.shared.transform),
      },
    };
  }
  return updateLayer(state, layerIndex, (layer) => ({
    ...layer,
    transform: update(layer.transform),
  }));
}
