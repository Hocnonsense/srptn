import type { TableSchema, VegaType } from "../schema/table-schema";
import type {
  CardinalityBand,
  FieldRole,
  SlotCardinality,
} from "./types";
import { CARDINALITY } from "./rules";

export interface FieldProfile {
  name: string;
  type: VegaType;
  role: FieldRole;
  cardinality: CardinalityBand;
  distinctCount: number;
  nullRatio: number;
  isConstant: boolean;
  isId: boolean;
  numeric?: number[];
  time?: number[];
  category?: (string | undefined)[];
}

export interface RecommendationProfile {
  table: TableSchema;
  n: number;
  fields: FieldProfile[];
  byName: Map<string, FieldProfile>;
  columnSignificance: Map<string, number>;
  pairSignificance: Map<string, number>;
}

export function createRecommendationProfile(
  table: TableSchema,
): RecommendationProfile {
  const n = table.rows.length;
  const fields = table.columns.map((column) => profileColumn(table, column.name, column.type));
  return {
    table,
    n,
    fields,
    byName: new Map(fields.map((field) => [field.name, field])),
    columnSignificance: new Map(),
    pairSignificance: new Map(),
  };
}

export function fieldUsable(field: FieldProfile): boolean {
  return (
    !field.isConstant &&
    !field.isId &&
    field.nullRatio < CARDINALITY.missingRatio
  );
}

export function roleMatches(field: FieldProfile, role: FieldRole): boolean {
  if (role === "measure") {
    return field.role === "measure";
  }
  if (role === "time") {
    return field.role === "time";
  }
  if (role === "dimension") {
    return field.role === "dimension";
  }
  return false;
}

export function cardinalityMatches(
  field: FieldProfile,
  cardinality: SlotCardinality | undefined,
): boolean {
  if (!cardinality || cardinality === "any") {
    return true;
  }
  if (cardinality === "low") {
    return field.distinctCount >= 2 && field.distinctCount <= CARDINALITY.lowMax;
  }
  if (cardinality === "medium") {
    return (
      field.distinctCount > CARDINALITY.lowMax &&
      field.distinctCount <= CARDINALITY.mediumMax
    );
  }
  return (
    field.distinctCount >= 2 &&
    field.distinctCount <= CARDINALITY.mediumMax
  );
}

export function significanceOf(
  profile: RecommendationProfile,
  fieldName: string,
): number {
  const cached = profile.columnSignificance.get(fieldName);
  if (cached !== undefined) {
    return cached;
  }
  const field = profile.byName.get(fieldName);
  const value = field ? columnSignificance(field) : 0;
  profile.columnSignificance.set(fieldName, value);
  return value;
}

export function pairSignificanceOf(
  profile: RecommendationProfile,
  left: string,
  right: string,
): number {
  if (left === right) {
    return 0;
  }
  const key = left < right ? `${left}\u0000${right}` : `${right}\u0000${left}`;
  const cached = profile.pairSignificance.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const a = profile.byName.get(left);
  const b = profile.byName.get(right);
  const value = a && b ? pairSignificance(a, b) : 0;
  profile.pairSignificance.set(key, value);
  return value;
}

function profileColumn(
  table: TableSchema,
  name: string,
  type: VegaType,
): FieldProfile {
  const values = table.rows.map((row) => row[name]);
  const nonNull = values.filter(
    (value) => value !== null && value !== undefined && value !== "",
  );
  const n = values.length;
  const role: FieldRole =
    type === "quantitative"
      ? "measure"
      : type === "temporal"
        ? "time"
        : "dimension";

  const numeric =
    role === "measure"
      ? values.map((value) => {
        const number = typeof value === "number" ? value : Number(value);
        return Number.isFinite(number) ? number : Number.NaN;
      })
      : undefined;
  const time =
    role === "time"
      ? values.map((value) => toTime(value) ?? Number.NaN)
      : undefined;
  const category =
    role === "dimension"
      ? values.map((value) =>
        value === null || value === undefined || value === ""
          ? undefined
          : String(value),
      )
      : undefined;

  const distinct = distinctCount({
    numeric,
    time,
    category,
    values,
  });
  const nullRatio = n === 0 ? 1 : 1 - nonNull.length / n;
  const isConstant = distinct <= 1;

  return {
    name,
    type,
    role,
    cardinality: cardinalityBand(distinct),
    distinctCount: distinct,
    nullRatio,
    isConstant,
    isId:
      role === "dimension" &&
      n >= CARDINALITY.idMinRows &&
      distinct / n >= CARDINALITY.idRatio,
    numeric,
    time,
    category,
  };
}

function distinctCount(values: {
  numeric?: number[];
  time?: number[];
  category?: (string | undefined)[];
  values: unknown[];
}): number {
  const source = values.numeric ?? values.time ?? values.category;
  if (!source) {
    return new Set(values.values.filter(isPresent)).size;
  }
  const seen = new Set<string>();
  for (const value of source) {
    if (typeof value === "number") {
      if (Number.isFinite(value)) {
        seen.add(String(value));
      }
    } else if (value !== undefined) {
      seen.add(value);
    }
  }
  return seen.size;
}

function cardinalityBand(distinct: number): CardinalityBand {
  if (distinct <= 1) {
    return "constant";
  }
  if (distinct === 2) {
    return "binary";
  }
  if (distinct <= CARDINALITY.lowMax) {
    return "low";
  }
  if (distinct <= CARDINALITY.mediumMax) {
    return "medium";
  }
  return "high";
}

function columnSignificance(field: FieldProfile): number {
  if (field.isConstant) {
    return 0;
  }
  let raw = 0;
  if (field.role === "measure" && field.numeric) {
    const values = field.numeric.filter(Number.isFinite);
    const mean = average(values);
    const sd = standardDeviation(values, mean);
    raw = sd / (Math.abs(mean) + sd + 1e-9);
  } else if (field.role === "time" && field.time) {
    const values = field.time.filter(Number.isFinite);
    raw = 1 - Math.exp(-new Set(values.map((value) => String(value))).size / 8);
  } else if (field.category) {
    const entropy = categoricalEntropy(field.category);
    const repetitions = 1 - field.distinctCount / Math.max(1, field.category.length);
    raw = entropy * Math.max(0, repetitions);
  }
  return clamp01(raw * (1 - field.nullRatio));
}

function pairSignificance(left: FieldProfile, right: FieldProfile): number {
  if (left.isConstant || right.isConstant) {
    return 0;
  }
  const n = pairedCount(left, right);
  if (n < 4) {
    return 0;
  }
  const shrink = n / (n + 6);
  if (isNumeric(left) && isNumeric(right)) {
    const pairs = pairedNumbers(left, right);
    const pearson = Math.abs(pearsonCorrelation(pairs.x, pairs.y));
    const spearman = Math.abs(
      pearsonCorrelation(rank(pairs.x), rank(pairs.y)),
    );
    return clamp01(Math.max(pearson, spearman) * shrink);
  }
  if (left.category && isNumeric(right)) {
    return clamp01(etaSquared(left.category, numericValues(right)) * shrink);
  }
  if (right.category && isNumeric(left)) {
    return clamp01(etaSquared(right.category, numericValues(left)) * shrink);
  }
  if (left.category && right.category) {
    const entropyLeft = categoricalEntropy(left.category);
    const entropyRight = categoricalEntropy(right.category);
    const denominator = Math.min(entropyLeft, entropyRight);
    if (denominator <= 0) {
      return 0;
    }
    return clamp01(
      (mutualInformation(left.category, right.category) / denominator) * shrink,
    );
  }
  return 0;
}

function isNumeric(field: FieldProfile): boolean {
  return Boolean(field.numeric || field.time);
}

function numericValues(field: FieldProfile): number[] {
  return field.numeric ?? field.time ?? [];
}

function pairedNumbers(
  left: FieldProfile,
  right: FieldProfile,
): { x: number[]; y: number[] } {
  const leftValues = numericValues(left);
  const rightValues = numericValues(right);
  const x: number[] = [];
  const y: number[] = [];
  for (let index = 0; index < leftValues.length; index += 1) {
    if (Number.isFinite(leftValues[index]) && Number.isFinite(rightValues[index])) {
      x.push(leftValues[index]);
      y.push(rightValues[index]);
    }
  }
  return { x, y };
}

function pairedCount(left: FieldProfile, right: FieldProfile): number {
  if (left.category && right.category) {
    return left.category.reduce(
      (count, value, index) =>
        value !== undefined && right.category?.[index] !== undefined
          ? count + 1
          : count,
      0,
    );
  }
  if (left.category && isNumeric(right)) {
    const values = numericValues(right);
    return left.category.reduce(
      (count, value, index) =>
        value !== undefined && Number.isFinite(values[index])
          ? count + 1
          : count,
      0,
    );
  }
  if (right.category && isNumeric(left)) {
    const values = numericValues(left);
    return right.category.reduce(
      (count, value, index) =>
        value !== undefined && Number.isFinite(values[index])
          ? count + 1
          : count,
      0,
    );
  }
  const leftValues = numericValues(left);
  const rightValues = numericValues(right);
  let count = 0;
  for (let index = 0; index < leftValues.length; index += 1) {
    if (
      Number.isFinite(leftValues[index]) &&
      Number.isFinite(rightValues[index])
    ) {
      count += 1;
    }
  }
  return count;
}

function etaSquared(
  groups: (string | undefined)[],
  values: number[],
): number {
  const byGroup = new Map<string, number[]>();
  const all: number[] = [];
  for (let index = 0; index < groups.length; index += 1) {
    const group = groups[index];
    const value = values[index];
    if (group === undefined || !Number.isFinite(value)) {
      continue;
    }
    all.push(value);
    const bucket = byGroup.get(group);
    if (bucket) {
      bucket.push(value);
    } else {
      byGroup.set(group, [value]);
    }
  }
  if (all.length < 3 || byGroup.size < 2) {
    return 0;
  }
  const overall = average(all);
  let between = 0;
  let total = 0;
  for (const value of all) {
    total += (value - overall) ** 2;
  }
  for (const bucket of byGroup.values()) {
    between += bucket.length * (average(bucket) - overall) ** 2;
  }
  return total === 0 ? 0 : between / total;
}

function pearsonCorrelation(left: number[], right: number[]): number {
  if (left.length < 2 || left.length !== right.length) {
    return 0;
  }
  const leftMean = average(left);
  const rightMean = average(right);
  let covariance = 0;
  let leftVariance = 0;
  let rightVariance = 0;
  for (let index = 0; index < left.length; index += 1) {
    const leftDelta = left[index] - leftMean;
    const rightDelta = right[index] - rightMean;
    covariance += leftDelta * rightDelta;
    leftVariance += leftDelta ** 2;
    rightVariance += rightDelta ** 2;
  }
  const denominator = Math.sqrt(leftVariance * rightVariance);
  return denominator === 0 ? 0 : covariance / denominator;
}

function categoricalEntropy(values: (string | undefined)[]): number {
  const counts = new Map<string, number>();
  let total = 0;
  for (const value of values) {
    if (value === undefined) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
    total += 1;
  }
  if (total === 0 || counts.size <= 1) {
    return 0;
  }
  let entropy = 0;
  for (const count of counts.values()) {
    const probability = count / total;
    entropy -= probability * Math.log(probability);
  }
  return entropy / Math.log(counts.size);
}

function mutualInformation(
  left: (string | undefined)[],
  right: (string | undefined)[],
): number {
  const joint = new Map<string, number>();
  const leftCounts = new Map<string, number>();
  const rightCounts = new Map<string, number>();
  let total = 0;
  for (let index = 0; index < left.length; index += 1) {
    const a = left[index];
    const b = right[index];
    if (a === undefined || b === undefined) {
      continue;
    }
    joint.set(`${a}\u0000${b}`, (joint.get(`${a}\u0000${b}`) ?? 0) + 1);
    leftCounts.set(a, (leftCounts.get(a) ?? 0) + 1);
    rightCounts.set(b, (rightCounts.get(b) ?? 0) + 1);
    total += 1;
  }
  if (total === 0) {
    return 0;
  }
  let information = 0;
  for (const [key, count] of joint) {
    const [a, b] = key.split("\u0000");
    const probability = count / total;
    const independent =
      ((leftCounts.get(a) ?? 0) / total) * ((rightCounts.get(b) ?? 0) / total);
    information += probability * Math.log(probability / independent);
  }
  return Math.max(0, information);
}

function rank(values: number[]): number[] {
  const indexed = values
    .map((value, index) => ({ value, index }))
    .filter((item) => Number.isFinite(item.value))
    .sort((left, right) => left.value - right.value);
  const result = new Array(values.length).fill(Number.NaN);
  let position = 0;
  while (position < indexed.length) {
    let end = position + 1;
    while (
      end < indexed.length &&
      indexed[end].value === indexed[position].value
    ) {
      end += 1;
    }
    const averageRank = (position + end - 1) / 2 + 1;
    for (let index = position; index < end; index += 1) {
      result[indexed[index].index] = averageRank;
    }
    position = end;
  }
  return result;
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values: number[], mean: number): number {
  if (values.length === 0) {
    return 0;
  }
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
    values.length;
  return Math.sqrt(variance);
}

function toTime(value: unknown): number | undefined {
  if (value instanceof Date) {
    return value.getTime();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value !== "") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? undefined : parsed;
  }
  return undefined;
}

function isPresent(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
