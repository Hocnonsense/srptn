import type { VegaType } from "../schema/table-schema";
import { enumOf, fieldAt, fieldsOf } from "../schema/vl-schema";

const COMMON_TIME_UNITS = [
  "year", "yearquarter", "yearmonth", "yearmonthdate", "yearweek",
  "quarter", "month", "week", "day", "date", "hours", "minutes",
  "seconds", "milliseconds",
];
const LOCAL_TIME_UNITS = [
  ...enumOf("#/definitions/LocalSingleTimeUnit"),
  ...enumOf("#/definitions/LocalMultiTimeUnit"),
];
export const TIME_UNITS = [
  ...COMMON_TIME_UNITS,
  ...LOCAL_TIME_UNITS.filter((unit) => !COMMON_TIME_UNITS.includes(unit)),
];

export const FILTER_OPS = [
  { value: "==", label: "=" },
  { value: "!=", label: "≠" },
  { value: ">", label: ">" },
  { value: ">=", label: "≥" },
  { value: "<", label: "<" },
  { value: "<=", label: "≤" },
  { value: "in", label: "in" },
] as const;

export interface FilterState {
  field: string;
  op: string;
  value: string;
}

interface CalculateState {
  as: string;
  expression: string;
}

interface BinState {
  field: string;
  maxbins?: number;
}

interface TimeUnitState {
  field: string;
  timeUnit: string;
}

interface PathBinding<T> {
  path: string;
  decode?: (raw: unknown) => T | undefined;
  encode?: (value: T) => unknown;
  optional?: boolean;
  placeholder?: string;
}

type Binding<T> = string | PathBinding<T>;

const TRANSFORM_KEY = "transformKey";

export interface DeriveCreateContext {
  field: string;
  quantitativeField?: string;
  temporalField?: string;
}

export interface DeriveControl<K extends string = string> {
  key: K;
  kind: "text" | "number" | "field" | "timeUnit";
  placeholder?: string;
  min?: number;
}

export interface DeriveSpec<
  S extends object,
  N extends object = S,
> {
  ref: string;
  nameKey: string;
  sourceKey?: keyof S & string;
  bindings: { [K in keyof S]: Binding<S[K]> };
  defaults?: Record<string, unknown>;
  name: (state: N) => string;
  outputType?: VegaType;
  encoding?: boolean;
  create: (context: DeriveCreateContext) => S;
  update: (state: S, patch: Partial<S>) => S;
}

type DeriveCodec<S extends object> = Pick<
  DeriveSpec<S, object>,
  "ref" | "bindings" | "defaults"
>;

function defineTransform<
  S extends object,
  N extends object = S,
>(spec: DeriveSpec<S, N>): DeriveSpec<S, N> {
  return spec;
}

const requiredFieldCache = new Map<string, string[]>();

function requiredFieldNames(reference: string): string[] {
  let names = requiredFieldCache.get(reference);
  if (!names) {
    names = fieldsOf(reference)
      .filter((field) => field.required)
      .map((field) => field.name);
    requiredFieldCache.set(reference, names);
  }
  return names;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readPath(source: unknown, path: string): unknown {
  let current = source;
  for (const part of path.split(".")) {
    if (!isRecord(current)) {
      return undefined;
    }
    current = current[part];
  }
  return current;
}

function writePath(
  target: Record<string, unknown>,
  path: string,
  value: unknown,
): void {
  const parts = path.split(".");
  let current = target;
  for (const part of parts.slice(0, -1)) {
    if (!isRecord(current[part])) {
      current[part] = {};
    }
    current = current[part] as Record<string, unknown>;
  }
  current[parts[parts.length - 1]] = value;
}

function decodeString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function decodeNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function fromVLTransform<S extends object>(
  transform: Record<string, unknown>,
  spec: DeriveCodec<S>,
): S | undefined {
  if (
    !requiredFieldNames(spec.ref).every((name) => name in transform)
  ) {
    return undefined;
  }
  const state: Partial<S> = {};
  for (const key of Object.keys(spec.bindings) as (keyof S & string)[]) {
    const binding = spec.bindings[key];
    const value = readPath(
      transform,
      typeof binding === "string" ? binding : binding.path,
    );
    if (typeof binding === "string" || !binding.decode) {
      state[key] = value as S[typeof key];
      continue;
    }
    const decoded = binding.decode(value);
    if (decoded === undefined && !binding.optional) {
      return undefined;
    }
    state[key] = decoded as S[typeof key];
  }
  return state as S;
}

function toVLTransform<S extends object>(
  state: S,
  spec: DeriveCodec<S>,
): Record<string, unknown> {
  const transform = structuredClone(spec.defaults ?? {});
  for (const key of Object.keys(spec.bindings) as (keyof S & string)[]) {
    const binding = spec.bindings[key];
    const value = state[key];
    if (value === undefined) {
      continue;
    }
    const encoded =
      typeof binding === "string"
        ? value
        : binding.encode
          ? binding.encode(value)
          : value;
    if (encoded === undefined) {
      continue;
    }
    writePath(
      transform,
      typeof binding === "string" ? binding : binding.path,
      encoded,
    );
  }
  return transform;
}

export const DERIVE_SPECS = {
  calculate: defineTransform<
    CalculateState,
    Pick<CalculateState, "as">
  >({
    ref: "#/definitions/CalculateTransform",
    nameKey: "as",
    bindings: {
      as: {
        path: "as",
        decode: decodeString,
        placeholder: "field name",
      },
      expression: {
        path: "calculate",
        decode: decodeString,
        placeholder: "datum.y + 1",
      },
    },
    name: (state) => state.as,
    create: ({ field }) => ({
      as: `${field}_calc`,
      expression: `datum.${field}`,
    }),
    update: (state, patch) => ({ ...state, ...patch }),
  }),
  bin: defineTransform<
    BinState,
    Pick<BinState, "field" | "maxbins">
  >({
    ref: "#/definitions/BinTransform",
    nameKey: "as",
    sourceKey: "field",
    bindings: {
      field: { path: "field", decode: decodeString },
      maxbins: {
        path: "bin.maxbins",
        decode: decodeNumber,
        encode: (value) => (value ? value : undefined),
        optional: true,
      },
    },
    defaults: { bin: true },
    name: (state) =>
      state.maxbins
        ? `bin(${state.field}, maxbins=${state.maxbins})`
        : `bin(${state.field})`,
    outputType: "quantitative",
    encoding: true,
    create: ({ field, quantitativeField }) => ({
      field: quantitativeField ?? field,
      maxbins: 10,
    }),
    update: (state, patch) => ({ ...state, ...patch }),
  }),
  timeUnit: defineTransform<
    TimeUnitState,
    Pick<TimeUnitState, "field" | "timeUnit">
  >({
    ref: "#/definitions/TimeUnitTransform",
    nameKey: "as",
    sourceKey: "field",
    bindings: {
      field: { path: "field", decode: decodeString },
      timeUnit: { path: "timeUnit", decode: decodeString },
    },
    name: (state) => `timeUnit(${state.field}, ${state.timeUnit})`,
    outputType: "temporal",
    encoding: true,
    create: ({ field, temporalField }) => ({
      field: temporalField ?? field,
      timeUnit: "yearmonth",
    }),
    update: (state, patch) => ({ ...state, ...patch }),
  }),
};

type Specs = typeof DERIVE_SPECS;
type StateOf<K extends keyof Specs> = Specs[K] extends DeriveSpec<infer S, infer _N> ? S : never;
type NameInputOf<K extends keyof Specs> = Specs[K] extends DeriveSpec<infer _S, infer N> ? N : never;

function specName(kind: keyof Specs, state: object): string {
  return (DERIVE_SPECS[kind].name as (input: object) => string)(state);
}

export function makeTransform<K extends keyof Specs>(
  kind: K,
  state: StateOf<K>,
): Record<string, unknown> {
  const transform = toVLTransform(
    state,
    DERIVE_SPECS[kind] as DeriveCodec<StateOf<K>>,
  );
  transform[DERIVE_SPECS[kind].nameKey] = specName(kind, state);
  transform[TRANSFORM_KEY] = kind;
  return transform;
}

export function readTransform<K extends keyof Specs>(
  kind: K,
  transform: Record<string, unknown>,
): StateOf<K> | undefined {
  if (transform[TRANSFORM_KEY] !== kind) {
    return undefined;
  }
  return fromVLTransform<StateOf<K>>(
    transform,
    DERIVE_SPECS[kind] as DeriveCodec<StateOf<K>>,
  );
}

type SpecOf<K extends keyof Specs> = {
  create: (context: DeriveCreateContext) => StateOf<K>;
  update: (
    state: StateOf<K>,
    patch: Partial<StateOf<K>>,
  ) => StateOf<K>;
};

export function isDeriveKind(value: string): value is keyof Specs {
  return Object.hasOwn(DERIVE_SPECS, value);
}

export function createDerivedTransform<K extends keyof Specs>(
  kind: K,
  context: DeriveCreateContext,
): Record<string, unknown> {
  const spec = DERIVE_SPECS[kind] as unknown as SpecOf<K>;
  return makeTransform(kind, spec.create(context));
}

export function updateDerivedTransform<K extends keyof Specs>(
  kind: K,
  transform: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const state = readTransform(kind, transform);
  if (!state) {
    return undefined;
  }
  const spec = DERIVE_SPECS[kind] as unknown as SpecOf<K>;
  return makeTransform(kind, spec.update(state, patch as Partial<StateOf<K>>));
}

function isTransformKey(value: string): boolean {
  return (
    Object.hasOwn(DERIVE_SPECS, value) ||
    value === "oneOf" ||
    value === "not" ||
    Object.hasOwn(PREDICATE_OPS, value)
  );
}

/** Input adapter: tag raw Vega-Lite transforms once when importing JSON. */
export function withTransformMetadata(
  transform: Record<string, unknown>,
): Record<string, unknown> {
  const existing = transform[TRANSFORM_KEY];
  if (typeof existing === "string" && isTransformKey(existing)) {
    return transform;
  }
  const kind = Object.keys(transform).find(
    (key): key is keyof Specs => Object.hasOwn(DERIVE_SPECS, key),
  );
  if (kind) {
    return { ...transform, [TRANSFORM_KEY]: kind };
  }
  if ("filter" in transform) {
    const predicateKey = predicateKeyOf(transform.filter);
    if (predicateKey) {
      return { ...transform, [TRANSFORM_KEY]: predicateKey };
    }
  }
  return transform;
}

/** Output adapter: remove editor metadata before emitting a Vega-Lite spec. */
export function toSpecTransforms(
  transforms: readonly Record<string, unknown>[],
): Record<string, unknown>[] {
  return transforms.map((transform) => {
    if (!(TRANSFORM_KEY in transform)) {
      return transform;
    }
    const result = { ...transform };
    delete result[TRANSFORM_KEY];
    return result;
  });
}

export function derivedName<K extends keyof Specs>(
  kind: K,
  state: NameInputOf<K>,
): string {
  return specName(kind, state);
}

export type DerivedTransformInfo = {
  [K in keyof Specs]: {
    kind: K;
    as: string;
    type?: VegaType;
    state: StateOf<K>;
    sourceField?: string;
    controls: DeriveControl<keyof StateOf<K> & string>[];
  };
}[keyof Specs];

function sourceFieldOf(
  kind: keyof Specs,
  state: StateOf<keyof Specs>,
): string | undefined {
  const sourceKey = DERIVE_SPECS[kind].sourceKey;
  if (!sourceKey) {
    return undefined;
  }
  const value = (state as Record<string, unknown>)[sourceKey];
  return typeof value === "string" ? value : undefined;
}

function controlsOf<K extends keyof Specs>(
  spec: Specs[K],
): DeriveControl<keyof StateOf<K> & string>[] {
  return (Object.keys(spec.bindings) as (keyof StateOf<K> & string)[]).map(
    (key) => {
      if (key === spec.sourceKey) {
        return { key, kind: "field" };
      }
      const binding = (spec.bindings as Record<string, Binding<unknown>>)[key];
      const path = typeof binding === "string" ? binding : binding.path;
      const placeholder =
        typeof binding === "string" ? undefined : binding.placeholder;
      if (path === "timeUnit") {
        return { key, kind: "timeUnit" };
      }
      const field = fieldAt(spec.ref, path);
      if (field?.type === "number" || field?.types?.includes("number")) {
        return {
          key,
          kind: "number",
          min: field.minimum,
          placeholder: placeholder ?? key,
        };
      }
      return { key, kind: "text", placeholder };
    },
  );
}

export function readDerivedTransform(
  transform: Record<string, unknown>,
): DerivedTransformInfo | undefined {
  const storedKind = transform[TRANSFORM_KEY];
  if (
    typeof storedKind !== "string" ||
    !Object.hasOwn(DERIVE_SPECS, storedKind)
  ) {
    return undefined;
  }
  const kind = storedKind as keyof Specs;
  const state = readTransform(kind, transform);
  if (!state) {
    return undefined;
  }
  const storedName = transform[DERIVE_SPECS[kind].nameKey];
  return {
    kind,
    as: typeof storedName === "string" ? storedName : specName(kind, state),
    type: DERIVE_SPECS[kind].outputType,
    state,
    sourceField: sourceFieldOf(kind, state),
    controls: controlsOf(DERIVE_SPECS[kind]),
  } as DerivedTransformInfo;
}

const PREDICATE_KEYS: Record<string, string> = {
  "==": "equal",
  ">": "gt",
  ">=": "gte",
  "<": "lt",
  "<=": "lte",
};
const PREDICATE_OPS = Object.fromEntries(
  Object.entries(PREDICATE_KEYS).map(([op, key]) => [key, op]),
);

function predicateKeyOf(value: unknown): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  if (value.oneOf !== undefined) {
    return "oneOf";
  }
  if (isRecord(value.not) && "equal" in value.not) {
    return "not";
  }
  return Object.keys(value).find((key) => Object.hasOwn(PREDICATE_OPS, key));
}

export function makeFilterTransform(
  filter: FilterState,
  type: VegaType,
): Record<string, unknown> {
  if (filter.op === "in") {
    return {
      [TRANSFORM_KEY]: "oneOf",
      filter: {
        field: filter.field,
        oneOf: filter.value
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean)
          .map((value) => coerce(value, type)),
      },
    };
  }
  const value = coerce(filter.value, type);
  if (filter.op === "!=") {
    return {
      [TRANSFORM_KEY]: "not",
      filter: { not: { field: filter.field, equal: value } },
    };
  }
  return {
    [TRANSFORM_KEY]: PREDICATE_KEYS[filter.op],
    filter: { field: filter.field, [PREDICATE_KEYS[filter.op]]: value },
  };
}

export function readFilterTransform(
  transform: Record<string, unknown>,
): FilterState | undefined {
  const filter = transform.filter;
  if (!filter || typeof filter !== "object" || Array.isArray(filter)) {
    return undefined;
  }
  const key = transform[TRANSFORM_KEY];
  if (typeof key !== "string") {
    return undefined;
  }
  const predicate = filter as Record<string, unknown>;
  if (key === "oneOf") {
    if (!predicate.field || predicate.oneOf === undefined) {
      return undefined;
    }
    return {
      field: String(predicate.field),
      op: "in",
      value: Array.isArray(predicate.oneOf)
        ? predicate.oneOf.map(String).join(", ")
        : String(predicate.oneOf),
    };
  }
  if (key === "not") {
    if (!isRecord(predicate.not) || !predicate.not.field) {
      return undefined;
    }
    const negated = predicate.not;
    if (!("equal" in negated)) {
      return undefined;
    }
    return {
      field: String(negated.field),
      op: "!=",
      value: String(negated.equal ?? ""),
    };
  }
  if (!Object.hasOwn(PREDICATE_OPS, key)) {
    return undefined;
  }
  const op = PREDICATE_OPS[key];
  if (!predicate.field || !(key in predicate)) {
    return undefined;
  }
  return {
    field: String(predicate.field),
    op,
    value: String(predicate[key] ?? ""),
  };
}

function coerce(value: string, type: VegaType): unknown {
  if (type === "quantitative") {
    const number = Number(value);
    return Number.isFinite(number) ? number : value;
  }
  return value;
}
