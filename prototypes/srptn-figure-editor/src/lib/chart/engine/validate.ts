import Ajv from "ajv";
import { Warn, type LoggerInterface } from "vega-util";
import { compile } from "vega-lite";

import { VL_SCHEMA } from "../schema/vl-schema";

export type Severity = "error" | "warning" | "info";

export interface ValidationIssue {
  severity: Severity;
  path: string;
  message: string;
}

const ajv = new Ajv({
  allErrors: true,
  strict: false,
  validateFormats: false,
});
const validateSchema = ajv.compile(VL_SCHEMA as object);

const MAX_SPEC_BYTES = 1_000_000;
const MAX_DEPTH = 64;

export interface ValidateOptions {
  forSave?: boolean;
}

export function validateSpec(
  spec: Record<string, unknown>,
  options: ValidateOptions = {},
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const size = specSize(spec);
  if ("error" in size) {
    return [
      {
        severity: "error",
        path: "<root>",
        message: size.error,
      },
    ];
  }
  if (size.bytes > MAX_SPEC_BYTES) {
    issues.push({
      severity: "error",
      path: "<root>",
      message: `Spec is larger than ${MAX_SPEC_BYTES} bytes.`,
    });
  }
  if (exceedsDepth(spec, MAX_DEPTH)) {
    issues.push({
      severity: "error",
      path: "<root>",
      message: `Spec nesting exceeds ${MAX_DEPTH} levels.`,
    });
  }

  if (!validateSchema(spec)) {
    for (const error of validateSchema.errors ?? []) {
      issues.push({
        severity: "error",
        path: error.instancePath || "<root>",
        message: error.message ?? "Schema validation failed.",
      });
    }
  }

  const logged: ValidationIssue[] = [];
  let loggerLevel = Warn;
  const logger = {} as LoggerInterface;
  logger.level = (level?: number) => {
    if (level === undefined) {
      return loggerLevel;
    }
    loggerLevel = level;
    return logger;
  };
  logger.warn = (...args: unknown[]) => {
    logged.push({
      severity: "warning",
      path: "<root>",
      message: formatLog(args),
    });
    return logger;
  };
  logger.error = (...args: unknown[]) => {
    logged.push({
      severity: "error",
      path: "<root>",
      message: formatLog(args),
    });
    return logger;
  };
  logger.info = () => logger;
  logger.debug = () => logger;

  try {
    compile(spec as never, { logger });
  } catch (error) {
    issues.push({
      severity: "error",
      path: "<root>",
      message: error instanceof Error ? error.message : String(error),
    });
  }
  issues.push(...logged);

  issues.push(...securityIssues(spec, options));
  return dedupe(issues);
}

export function securityIssues(
  spec: Record<string, unknown>,
  options: ValidateOptions = {},
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const data = spec.data;
  const datasets = Array.isArray(data) ? data : [data];
  datasets.forEach((dataset, index) => {
    if (!isRecord(dataset)) {
      return;
    }
    const base = Array.isArray(data) ? `/data/${index}` : "/data";
    if ("url" in dataset) {
      issues.push({
        severity: "error",
        path: `${base}/url`,
        message: "External data URLs are not allowed in figure specs.",
      });
    }
    if ("values" in dataset && options.forSave) {
      issues.push({
        severity: "warning",
        path: `${base}/values`,
        message: "Inline data is replaced by the bound artifact on save.",
      });
    }
  });

  for (const [channel, value] of [
    ["href", findChannel(spec, "href")],
    ["url", findChannel(spec, "url")],
  ] as const) {
    if (value && options.forSave) {
      issues.push({
        severity: "error",
        path: `/encoding/${channel}`,
        message: `${channel} encodings are not allowed in saved specs.`,
      });
    }
  }

  return issues;
}

function findChannel(
  spec: Record<string, unknown>,
  channel: string,
  seen: Set<unknown> = new Set(),
): unknown {
  if (seen.has(spec)) {
    return undefined;
  }
  seen.add(spec);
  const encoding = spec.encoding;
  if (isRecord(encoding) && encoding[channel]) {
    return encoding[channel];
  }
  if (Array.isArray(spec.layer)) {
    for (const layer of spec.layer) {
      const found = isRecord(layer)
        ? findChannel(layer, channel, seen)
        : undefined;
      if (found) {
        return found;
      }
    }
  }
  const inner = spec.spec;
  if (isRecord(inner)) {
    return findChannel(inner, channel, seen);
  }
  return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function specSize(
  spec: Record<string, unknown>,
): { bytes: number } | { error: string } {
  try {
    const encoded = JSON.stringify(spec);
    if (typeof encoded !== "string") {
      return { error: "Spec could not be serialized to JSON." };
    }
    return { bytes: new TextEncoder().encode(encoded).length };
  } catch (error) {
    return {
      error: `Spec could not be serialized to JSON: ${
        error instanceof Error ? error.message : String(error)
      }`,
    };
  }
}

function exceedsDepth(value: unknown, maxDepth: number): boolean {
  const stack: { value: unknown; depth: number }[] = [
    { value, depth: 1 },
  ];
  while (stack.length > 0) {
    const item = stack.pop()!;
    if (!item.value || typeof item.value !== "object") {
      continue;
    }
    if (item.depth > maxDepth) {
      return true;
    }
    const children = Array.isArray(item.value)
      ? item.value
      : Object.values(item.value);
    for (const child of children) {
      stack.push({ value: child, depth: item.depth + 1 });
    }
  }
  return false;
}

function formatLog(args: unknown[]): string {
  return args
    .map((value) => {
      if (typeof value === "string") {
        return value;
      }
      try {
        return JSON.stringify(value) ?? String(value);
      } catch {
        return String(value);
      }
    })
    .join(" ");
}

function dedupe(issues: ValidationIssue[]): ValidationIssue[] {
  const seen = new Set<string>();
  return issues.filter((issue) => {
    const key = `${issue.severity}:${issue.path}:${issue.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}
