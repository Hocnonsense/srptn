import type { ChartState, ChannelState, Scope } from "../state/types";

export function renameFieldInState(
  state: ChartState,
  layerIndex: number,
  scope: Scope,
  oldName: string,
  newName: string,
): ChartState {
  const next = structuredClone(state);

  if (scope === "shared") {
    renameEncoding(next.shared.encoding);
    for (const transform of next.shared.transform) {
      walk(transform);
    }
    for (const layer of next.layers) {
      renameEncoding(layer.encoding);
      for (const transform of layer.transform) {
        walk(transform);
      }
    }
  } else {
    const layer = next.layers[layerIndex];
    if (layer) {
      renameEncoding(layer.encoding);
      for (const transform of layer.transform) {
        walk(transform);
      }
    }
  }

  return next;

  function renameEncoding(encoding: Record<string, ChannelState>) {
    for (const channelState of Object.values(encoding)) {
      if (channelState.field === oldName) {
        channelState.field = newName;
      }
    }
  }

  function walk(value: unknown) {
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
      if (key === "field" && child === oldName) {
        record[key] = newName;
        continue;
      }
      if (
        (key === "calculate" || key === "filter") &&
        typeof child === "string"
      ) {
        record[key] = renameExpression(child, oldName, newName);
        continue;
      }
      if (
        (key === "groupby" || key === "partitionBy") &&
        Array.isArray(child)
      ) {
        record[key] = child.map((item) =>
          item === oldName ? newName : item,
        );
        continue;
      }
      walk(child);
    }
  }
}

function renameExpression(
  expression: string,
  oldName: string,
  newName: string,
): string {
  const escaped = oldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const dot = new RegExp(`datum\\.${escaped}(?![A-Za-z0-9_])`, "g");
  const bracket = new RegExp(
    `datum\\[\\s*(["'])${escaped}\\1\\s*\\]`,
    "g",
  );
  const access = fieldAccess(newName);
  return expression.replace(dot, access).replace(bracket, access);
}

function fieldAccess(name: string): string {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)
    ? `datum.${name}`
    : `datum[${JSON.stringify(name)}]`;
}
