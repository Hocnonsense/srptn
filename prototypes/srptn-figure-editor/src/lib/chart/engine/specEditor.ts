import LZString from "lz-string";

import type { ChartState } from "../state/types";
import { buildSpec } from "./buildSpec";
import { parseSpec } from "./parseSpec";
import { readDerivedTransform, readFilterTransform } from "./transforms";
import type { ValidationIssue } from "./validate";
import { validateSpec } from "./validate";
import { validateChartState } from "./validateState";

export const LOCKED_DATA = "locked -- uneditable";

const VEGA_EDITOR_URL = "https://vega.github.io/editor/#/url/vega-lite/";

export function vegaEditorUrl(spec: Record<string, unknown>): string {
  const serialized = LZString.compressToEncodedURIComponent(
    JSON.stringify(spec),
  );
  return `${VEGA_EDITOR_URL}${serialized}`;
}

const CHANNEL_KEYS = new Set([
  "field",
  "type",
  "aggregate",
  "bin",
  "timeUnit",
  "scale",
  "axis",
  "legend",
  "header",
]);

export interface EditableSpecResult {
  state?: ChartState;
  spec?: Record<string, unknown>;
  issues: ValidationIssue[];
  error?: string;
  unsupported: string[];
}

export function editableSpec(spec: Record<string, unknown>) {
  const clone = structuredClone(spec);
  clone.data = LOCKED_DATA;
  return clone;
}

export function editableSpecText(spec: Record<string, unknown>) {
  return JSON.stringify(editableSpec(spec), null, 2);
}

export function parseEditableSpec(text: string): EditableSpecResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    return {
      issues: [],
      error: error instanceof Error ? error.message : String(error),
      unsupported: [],
    };
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { issues: [], error: "Spec must be a JSON object.", unsupported: [] };
  }
  const record = parsed as Record<string, unknown>;
  if (record.data !== LOCKED_DATA) {
    return {
      issues: [],
      error: `data is locked and must stay as "${LOCKED_DATA}".`,
      unsupported: [],
    };
  }

  const canonical = { ...record, data: { name: "data" } };
  const state = parseSpec(canonical);
  const spec = buildSpec(state, { includeData: false });
  const issues = [...validateChartState(state), ...validateSpec(spec)];
  const errors = issues.filter((issue) => issue.severity === "error");
  if (errors.length > 0) {
    return {
      issues,
      error: errors.map((issue) => `${issue.path}: ${issue.message}`).join("\n"),
      unsupported: unsupportedPaths(state),
    };
  }

  return { state, spec, issues, unsupported: unsupportedPaths(state) };
}

export function unsupportedPaths(state: ChartState): string[] {
  const paths: string[] = [];
  const push = (value: unknown, base: string) => {
    if (Array.isArray(value)) {
      if (value.length === 0) {
        paths.push(base);
        return;
      }
      value.forEach((item, index) => push(item, `${base}/${index}`));
      return;
    }
    if (value && typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) {
        paths.push(base);
        return;
      }
      for (const [key, item] of entries) {
        push(item, `${base}/${encodePart(key)}`);
      }
      return;
    }
    paths.push(base);
  };

  for (const [key, value] of Object.entries(state.extras)) {
    push(value, `/${encodePart(key)}`);
  }
  for (const [channel, channelState] of Object.entries(state.shared.encoding)) {
    for (const [key, value] of Object.entries(channelState)) {
      if (!CHANNEL_KEYS.has(key)) {
        push(
          value,
          `/shared/encoding/${encodePart(channel)}/${encodePart(key)}`,
        );
      }
    }
  }
  state.shared.transform.forEach((transform, index) => {
    if (!isKnownTransform(transform)) {
      paths.push(`/shared/transform/${index}`);
    }
  });
  for (const [channel, value] of Object.entries(
    state.shared.raw?.encoding ?? {},
  )) {
    push(value, `/shared/raw/encoding/${encodePart(channel)}`);
  }
  (state.shared.raw?.transforms ?? []).forEach((value, index) => {
    push(value, `/shared/raw/transforms/${index}`);
  });
  state.layers.forEach((layer, layerIndex) => {
    for (const [key, value] of Object.entries(layer.extras)) {
      push(value, `/layers/${layerIndex}/${encodePart(key)}`);
    }
    for (const [channel, channelState] of Object.entries(layer.encoding)) {
      for (const [key, value] of Object.entries(channelState)) {
        if (!CHANNEL_KEYS.has(key)) {
          push(
            value,
            `/layers/${layerIndex}/encoding/${encodePart(channel)}/${encodePart(key)}`,
          );
        }
      }
    }
    layer.transform.forEach((transform, transformIndex) => {
      if (!isKnownTransform(transform)) {
        paths.push(`/layers/${layerIndex}/transform/${transformIndex}`);
      }
    });
    for (const [channel, value] of Object.entries(
      layer.raw?.encoding ?? {},
    )) {
      push(
        value,
        `/layers/${layerIndex}/raw/encoding/${encodePart(channel)}`,
      );
    }
    (layer.raw?.transforms ?? []).forEach((value, index) => {
      push(value, `/layers/${layerIndex}/raw/transforms/${index}`);
    });
  });
  return [...new Set(paths)];
}

function isKnownTransform(transform: Record<string, unknown>): boolean {
  return (
    Array.isArray(transform.aggregate) ||
    Boolean(readDerivedTransform(transform)) ||
    Boolean(readFilterTransform(transform))
  );
}

function encodePart(part: string): string {
  return part.replace(/~/g, "~0").replace(/\//g, "~1");
}

function decodePart(part: string): string {
  return part.replace(/~1/g, "/").replace(/~0/g, "~");
}


export function getAtPath(state: ChartState, path: string): unknown {
  const parts = path.split("/").filter(Boolean).map(decodePart);
  let current: unknown = state;
  for (const part of parts) {
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index)) {
        return undefined;
      }
      current = current[index];
    } else if (current && typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

export function setAtPath(
  state: ChartState,
  path: string,
  value: unknown,
): ChartState {
  const parts = path.split("/").filter(Boolean).map(decodePart);
  if (parts.length === 0) {
    return state;
  }
  const next = structuredClone(state);
  let current: Record<string, unknown> | unknown[] = next as unknown as Record<
    string,
    unknown
  >;
  for (let index = 0; index < parts.length - 1; index += 1) {
    const part = parts[index];
    const nextPart = parts[index + 1];
    const key = Array.isArray(current) ? Number(part) : part;
    if (Array.isArray(current) && !Number.isInteger(key)) {
      return state;
    }
    const existing = Array.isArray(current)
      ? current[key as number]
      : (current as Record<string, unknown>)[key as string];
    if (!existing || typeof existing !== "object") {
      const child: Record<string, unknown> | unknown[] =
        /^\d+$/.test(nextPart) ? [] : {};
      if (Array.isArray(current)) {
        current[key as number] = child;
      } else {
        (current as Record<string, unknown>)[key as string] = child;
      }
    }
    current = (
      Array.isArray(current)
        ? current[key as number]
        : (current as Record<string, unknown>)[key as string]
    ) as Record<string, unknown> | unknown[];
  }

  const key = parts[parts.length - 1];
  if (Array.isArray(current)) {
    const index = Number(key);
    if (!Number.isInteger(index)) {
      return state;
    }
    if (value === undefined) {
      current.splice(index, 1);
    } else {
      current[index] = value;
    }
  } else if (value === undefined) {
    delete (current as Record<string, unknown>)[key];
  } else {
    (current as Record<string, unknown>)[key] = value;
  }
  return next;
}
