import type { VegaType } from "../schema/table-schema";
import { readDerivedTransform } from "./transforms";
import type { ValidationIssue } from "./validate";

interface DerivedField {
  name: string;
  source: "calculate" | "bin" | "timeUnit";
  type?: VegaType;
  transformIndex: number;
}

export function derivedFields(
  baseNames: readonly string[],
  transforms: readonly Record<string, unknown>[],
): DerivedField[] {
  const taken = new Set(baseNames);
  const fields: DerivedField[] = [];
  transforms.forEach((transform, transformIndex) => {
    const output = transformOutput(transform);
    if (!output) {
      return;
    }
    const name = output.as.trim();
    if (!name || taken.has(name)) {
      return;
    }
    taken.add(name);
    fields.push({
      name,
      source: output.source,
      type: output.type,
      transformIndex,
    });
  });
  return fields;
}

export function fieldIssues(
  baseNames: readonly string[],
  transforms: readonly Record<string, unknown>[],
  pathPrefix: string,
): ValidationIssue[] {
  const taken = new Set(baseNames);
  const issues: ValidationIssue[] = [];
  transforms.forEach((transform, index) => {
    const output = transformOutput(transform);
    if (!output) {
      return;
    }
    const name = output.as.trim();
    if (!name) {
      issues.push({
        severity: "error",
        path: `${pathPrefix}/transform/${index}/as`,
        message: "Derived field name is required.",
      });
      return;
    }
    if (taken.has(name)) {
      issues.push({
        severity: "error",
        path: `${pathPrefix}/transform/${index}/as`,
        message: `Field '${name}' already exists in this scope.`,
      });
      return;
    }
    taken.add(name);
  });
  return issues;
}

function transformOutput(
  transform: Record<string, unknown>,
):
  | {
    as: string;
    source: DerivedField["source"];
    type?: VegaType;
  }
  | undefined {
  const derived = readDerivedTransform(transform);
  if (!derived) {
    return undefined;
  }
  return { as: derived.as, source: derived.kind, type: derived.type };
}
