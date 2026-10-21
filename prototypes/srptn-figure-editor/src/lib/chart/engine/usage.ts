import type { ChartState, ChannelState, Scope } from "../state/types";
import { readDerivedTransform } from "./transforms";

export function unusedOutputs(
  state: ChartState,
  scope: Scope,
  layerIndex: number,
): Set<string> {
  const referenced = new Set<string>();
  let certain = true;

  const addEncoding = (encoding: Record<string, ChannelState>) => {
    for (const channelState of Object.values(encoding)) {
      if (typeof channelState.field === "string") {
        referenced.add(channelState.field);
      }
    }
  };

  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      for (const item of value) {
        walk(item);
      }
      return;
    }
    if (!value || typeof value !== "object") {
      return;
    }
    const record = value as Record<string, unknown>;
    for (const [key, child] of Object.entries(record)) {
      if (key === "field" && typeof child === "string") {
        referenced.add(child);
        continue;
      }
      if (
        (key === "groupby" || key === "partitionBy") &&
        Array.isArray(child)
      ) {
        for (const item of child) {
          if (typeof item === "string") {
            referenced.add(item);
          }
        }
        continue;
      }
      if (
        (key === "calculate" || key === "filter") &&
        typeof child === "string"
      ) {
        const parsed = expressionFields(child);
        for (const field of parsed.fields) {
          referenced.add(field);
        }
        certain = certain && parsed.certain;
        continue;
      }
      walk(child);
    }
  };

  if (scope === "shared") {
    addEncoding(state.shared.encoding);
    for (const transform of state.shared.transform) {
      walk(transform);
    }
    for (const layer of state.layers) {
      addEncoding(layer.encoding);
      for (const transform of layer.transform) {
        walk(transform);
      }
    }
  } else {
    const layer = state.layers[layerIndex];
    if (!layer) {
      return new Set();
    }
    addEncoding(layer.encoding);
    for (const transform of layer.transform) {
      walk(transform);
    }
  }

  if (!certain) {
    return new Set();
  }

  const transforms =
    scope === "shared"
      ? state.shared.transform
      : (state.layers[layerIndex]?.transform ?? []);
  const unused = new Set<string>();
  for (const transform of transforms) {
    for (const output of transformOutputs(transform)) {
      if (!referenced.has(output)) {
        unused.add(output);
      }
    }
  }
  return unused;
}

function transformOutputs(transform: Record<string, unknown>): string[] {
  const outputs: string[] = [];
  if (Array.isArray(transform.aggregate)) {
    for (const entry of transform.aggregate) {
      if (
        entry &&
        typeof entry === "object" &&
        !Array.isArray(entry) &&
        typeof (entry as Record<string, unknown>).as === "string"
      ) {
        outputs.push(String((entry as Record<string, unknown>).as));
      }
    }
  }
  const derived = readDerivedTransform(transform);
  if (derived) {
    outputs.push(derived.as);
  } else if (typeof transform.as === "string") {
    outputs.push(transform.as);
  }
  return outputs;
}

function expressionFields(expression: string): {
  fields: string[];
  certain: boolean;
} {
  const fields = new Set<string>();
  let certain = true;

  for (const match of expression.matchAll(
    /\bdatum\.([A-Za-z_][A-Za-z0-9_]*)/g,
  )) {
    fields.add(match[1]);
  }
  for (const match of expression.matchAll(
    /datum\[\s*(["'])(.*?)\1\s*\]/g,
  )) {
    fields.add(match[2]);
  }

  if (/\bdatum\s*\[/.test(expression) && !/datum\[\s*["']/.test(expression)) {
    certain = false;
  }
  if (/\bdatum\b/.test(expression) && fields.size === 0) {
    certain = false;
  }

  return { fields: [...fields], certain };
}
