import type { ChartState } from "../state/types";
import type { PatchOp } from "./types";

export function applyChartPatch(
  baseline: ChartState,
  ops: readonly PatchOp[],
): ChartState {
  let next = clone(baseline);
  for (const op of ops) {
    if (op.path.length === 0) {
      if (op.op === "remove") {
        throw new Error("Cannot remove the chart state root.");
      }
      next = clone(op.value) as ChartState;
      continue;
    }
    const parent = parentAt(next, op.path);
    const key = op.path[op.path.length - 1];
    if (op.op === "remove") {
      if (Array.isArray(parent) && typeof key === "number") {
        parent.splice(key, 1);
      } else {
        delete (parent as Record<string, unknown>)[String(key)];
      }
    } else if (Array.isArray(parent) && typeof key === "number") {
      parent[key] = clone(op.value);
    } else {
      (parent as Record<string, unknown>)[String(key)] = clone(op.value);
    }
  }
  return next;
}

export function diffChartState(
  baseline: ChartState,
  candidate: ChartState,
): PatchOp[] {
  const ops: PatchOp[] = [];
  walk(baseline, candidate, [], ops);
  return ops;
}

function walk(
  baseline: unknown,
  candidate: unknown,
  path: (string | number)[],
  ops: PatchOp[],
): void {
  if (candidate === undefined) {
    if (baseline !== undefined) {
      ops.push({ op: "remove", path: [...path] });
    }
    return;
  }
  if (isRecord(baseline) && isRecord(candidate)) {
    const keys = new Set([
      ...Object.keys(baseline),
      ...Object.keys(candidate),
    ]);
    for (const key of keys) {
      walk(baseline[key], candidate[key], [...path, key], ops);
    }
    return;
  }
  if (
    Array.isArray(baseline) &&
    Array.isArray(candidate) &&
    baseline.length === candidate.length
  ) {
    for (let index = 0; index < baseline.length; index += 1) {
      walk(baseline[index], candidate[index], [...path, index], ops);
    }
    return;
  }
  if (deepEqual(baseline, candidate)) {
    return;
  }
  ops.push({ op: "set", path: [...path], value: clone(candidate) });
}

function parentAt(
  root: unknown,
  path: (string | number)[],
): unknown {
  let current = root;
  for (let index = 0; index < path.length - 1; index += 1) {
    current = (current as Record<string | number, unknown>)[path[index]];
  }
  return current;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true;
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return (
      left.length === right.length &&
      left.every((item, index) => deepEqual(item, right[index]))
    );
  }
  if (isRecord(left) && isRecord(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every(
        (key) =>
          Object.hasOwn(right, key) && deepEqual(left[key], right[key]),
      )
    );
  }
  return false;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}
