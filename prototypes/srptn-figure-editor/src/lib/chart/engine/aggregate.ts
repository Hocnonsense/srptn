import type { VegaType } from "../schema/table-schema";
import type { ChannelState } from "../state/types";
import { readDerivedTransform } from "./transforms";
import type { ValidationIssue } from "./validate";

export interface AggregateOutput {
  name: string;
  op: string;
  field?: string;
}

export function collectAggregateOps(
  transforms: readonly Record<string, unknown>[],
): AggregateOutput[] {
  const outputs: AggregateOutput[] = [];
  for (const transform of transforms) {
    if (!Array.isArray(transform.aggregate)) {
      continue;
    }
    for (const entry of transform.aggregate) {
      if (
        !isRecord(entry) ||
        typeof entry.op !== "string" ||
        typeof entry.as !== "string"
      ) {
        continue;
      }
      const field = typeof entry.field === "string" ? entry.field : undefined;
      outputs.push(
        field
          ? { name: entry.as, op: entry.op, field }
          : { name: entry.as, op: entry.op },
      );
    }
  }
  return outputs;
}

export function aggregateIssues(
  baseNames: readonly string[],
  transforms: readonly Record<string, unknown>[],
  pathPrefix: string,
): ValidationIssue[] {
  const names = new Set(baseNames);
  const ops = new Set<string>();
  const issues: ValidationIssue[] = [];
  transforms.forEach((transform, index) => {
    if (!Array.isArray(transform.aggregate)) {
      return;
    }
    transform.aggregate.forEach((entry, opIndex) => {
      if (!isRecord(entry)) {
        return;
      }
      const path = `${pathPrefix}/transform/${index}/aggregate/${opIndex}`;
      const op = typeof entry.op === "string" ? entry.op : undefined;
      const field = typeof entry.field === "string" ? entry.field : undefined;
      const name = typeof entry.as === "string" ? entry.as.trim() : "";
      if (!op) {
        issues.push({
          severity: "error",
          path: `${path}/op`,
          message: "Aggregate operation is required.",
        });
        return;
      }
      if (!name) {
        issues.push({
          severity: "error",
          path: `${path}/as`,
          message: "Aggregate field name is required.",
        });
        return;
      }
      const key = `${op}\u0000${field ?? ""}`;
      if (ops.has(key)) {
        issues.push({
          severity: "error",
          path,
          message: `Duplicate aggregate ${op}(${field ?? ""}) in this scope.`,
        });
      } else {
        ops.add(key);
      }
      if (names.has(name)) {
        issues.push({
          severity: "error",
          path: `${path}/as`,
          message: `Field '${name}' already exists in this scope.`,
        });
      } else {
        names.add(name);
      }
    });
  });
  return issues;
}

export function upsertAggregate(
  transforms: readonly Record<string, unknown>[],
  op: string,
  field: string | undefined,
): {
  transforms: Record<string, unknown>[];
  output: AggregateOutput;
} {
  const existing = collectAggregateOps(transforms);
  const match = existing.find(
    (item) => item.op === op && item.field === field,
  );
  if (match) {
    return { transforms: [...transforms], output: match };
  }

  const name = aggregateName(op, field);
  const entry = field ? { op, field, as: name } : { op, as: name };
  const next = [...transforms];
  const index = next.findIndex(isAggregateTransform);
  if (index >= 0) {
    const transform = next[index];
    next[index] = {
      ...transform,
      aggregate: [...(transform.aggregate as unknown[]), entry],
    };
  } else {
    next.push({ aggregate: [entry] });
  }

  return {
    transforms: next,
    output: field ? { name, op, field } : { name, op },
  };
}

export function finalizeTransforms(
  transforms: readonly Record<string, unknown>[],
  encoding: Record<string, ChannelState>,
  exclude: ReadonlySet<string> = new Set(),
): Record<string, unknown>[] {
  const aggregateIndex = transforms.findIndex(isAggregateTransform);
  if (aggregateIndex < 0) {
    return [...transforms];
  }

  const result = transforms.map((transform) => ({ ...transform }));
  const outputs = collectAggregateOps(transforms);
  const outputNames = new Set(outputs.map((output) => output.name));
  const postCalculateNames = new Set(
    transforms
      .slice(aggregateIndex + 1)
      .map(derivedOutputName)
      .filter((name): name is string => Boolean(name)),
  );

  const groupby = new Set<string>();
  for (const channelState of Object.values(encoding)) {
    if (
      typeof channelState.field === "string" &&
      !outputNames.has(channelState.field) &&
      !postCalculateNames.has(channelState.field) &&
      !exclude.has(channelState.field)
    ) {
      groupby.add(channelState.field);
    }
  }

  const aggregate = result[aggregateIndex];
  const ops = Array.isArray(aggregate.aggregate) ? aggregate.aggregate : [];
  result[aggregateIndex] = { ...aggregate, aggregate: ops };
  if (!Array.isArray(aggregate.groupby)) {
    if (groupby.size > 0) {
      result[aggregateIndex].groupby = [...groupby];
    } else {
      delete result[aggregateIndex].groupby;
    }
  }

  return result;
}

export function aggregateOutputType(
  op: string,
  type?: VegaType,
): VegaType {
  if (
    op === "count" ||
    op === "mean" ||
    op === "sum" ||
    op === "median"
  ) {
    return "quantitative";
  }
  return type ?? "quantitative";
}

export function aggregateName(
  op: string,
  field: string | undefined,
): string {
  return `${op}(${field ?? ""})`;
}

function isAggregateTransform(transform: Record<string, unknown>): boolean {
  return Array.isArray(transform.aggregate);
}

function derivedOutputName(
  transform: Record<string, unknown>,
): string | undefined {
  return readDerivedTransform(transform)?.as;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
