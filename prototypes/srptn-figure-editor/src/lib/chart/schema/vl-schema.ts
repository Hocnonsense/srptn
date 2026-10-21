import rawSchema from "vega-lite/vega-lite-schema.json";

export interface JsonSchema {
  $ref?: string;
  $schema?: string;
  description?: string;
  title?: string;
  type?: string | string[];
  enum?: unknown[];
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  allOf?: JsonSchema[];
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  definitions?: Record<string, JsonSchema>;
  minimum?: number;
  maximum?: number;
  multipleOf?: number;
  default?: unknown;
  [key: string]: unknown;
}

export const VL_SCHEMA = rawSchema as unknown as JsonSchema;
export const VL_SCHEMA_URL = "https://vega.github.io/schema/vega-lite/v6.json";

/** RFC 6901 convert a JSON pointer part
 * `~1` -> `/`
 * `~0` -> `~`
*/
function decodePointerPart(part: string): string {
  return part.replace(/~1/g, "/").replace(/~0/g, "~");
}
function encodePointerPart(part: string): string {
  return part.replace(/~/g, "~0").replace(/\//g, "~1");
}

/** Convert a list of parts into a JSON pointer. */
export function pointer(...parts: string[]): string {
  return "#/" + parts.map(encodePointerPart).join("/");
}
/** Get the sub schema at the reference pointer from the input schema.
 *
 * Local references only, no external URL dereferencing.
 *
 * for each part, the search order is:
 * 1. Special segment `definitions` or `$defs`;
 * 2. Property names in `properties`;
 * 3. Key in the current node's `definitions` object;
 * 4. Fallback: treat the current node as a regular object and access its properties by name.
 *
 * @param schema The origin schema
 * @param reference JSON Pointer e.g., `#/definitions/Mark/type`
 * @returns resolved schema node, or `undefined` if the reference is invalid or missing
 */
export function resolvePointer(
  schema: JsonSchema,
  reference: string,
): JsonSchema | undefined {
  if (!reference.startsWith("#/")) {
    return undefined;
  }
  let current: JsonSchema | undefined = schema;
  for (const rawPart of reference.slice(2).split("/")) {
    if (!current) {
      return undefined;
    }
    const part = decodePointerPart(rawPart);
    if (part === "definitions" && current.definitions) {
      current = current.definitions;
      continue;
    }
    if (part === "$defs" && current.$defs) {
      current = current.$defs as JsonSchema;
      continue;
    }
    if (current.properties?.[part]) {
      current = current.properties[part];
      continue;
    }
    if (current.definitions?.[part]) {
      current = current.definitions[part];
      continue;
    }
    current = (current as Record<string, unknown>)[part] as
      | JsonSchema
      | undefined;
  }
  return current;
}

/**
 * dereference for `$ref` nodes, trace until the real definition
 *
 * @param schema The schema to resolve the reference in
 * @param node The node to dereference (could be a regular node, a `$ref` node, or `undefined`)
 * @returns object:
 * - `schema`: deferenced schema node, or `undefined` if the reference is invalid or missing
 * - `reference`: the last `$ref` string encountered during dereferencing, or `undefined` if the input node was not a `$ref`
 */
export function deref(
  schema: JsonSchema,
  node: JsonSchema | undefined,
): { schema: JsonSchema | undefined; reference?: string } {
  let current = node;
  let reference: string | undefined;
  /** avoid circular references */
  const seen = new Set<string>();
  while (current?.$ref) {
    if (seen.has(current.$ref)) {
      break;
    }
    seen.add(current.$ref);
    reference = current.$ref;
    current = resolvePointer(schema, current.$ref);
  }
  return { schema: current, reference };
}
/** Get referenced sub schema of vega-lite */
export function schemaAt(reference: string): JsonSchema | undefined {
  return deref(VL_SCHEMA, resolvePointer(VL_SCHEMA, reference)).schema;
}

function collectEnum(
  node: JsonSchema | undefined,
  seen: Set<string> = new Set(),
): string[] {
  if (!node) {
    return [];
  }
  if (node.$ref) {
    if (seen.has(node.$ref)) {
      return [];
    }
    seen.add(node.$ref);
    return collectEnum(resolvePointer(VL_SCHEMA, node.$ref), seen);
  }
  const values = new Set<string>();
  if (Array.isArray(node.enum)) {
    for (const value of node.enum) {
      if (typeof value === "string") {
        values.add(value);
      }
    }
  }
  for (const branch of node.anyOf ?? node.oneOf ?? node.allOf ?? []) {
    for (const value of collectEnum(branch, seen)) {
      values.add(value);
    }
  }
  return [...values];
}
export function enumOf(reference: string): string[] {
  return collectEnum(schemaAt(reference));
}

function collectRange(
  node: JsonSchema | undefined,
): { minimum?: number; maximum?: number; multipleOf?: number } {
  if (!node) {
    return {};
  }
  const own = {
    minimum: typeof node.minimum === "number" ? node.minimum : undefined,
    maximum: typeof node.maximum === "number" ? node.maximum : undefined,
    multipleOf:
      typeof node.multipleOf === "number" ? node.multipleOf : undefined,
  };
  if (
    own.minimum !== undefined ||
    own.maximum !== undefined ||
    own.multipleOf !== undefined
  ) {
    return own;
  }
  for (const branch of node.anyOf ?? node.oneOf ?? node.allOf ?? []) {
    const found = collectRange(branch);
    if (Object.values(found).some((value) => value !== undefined)) {
      return found;
    }
  }
  return {};
}
export function rangeOf(reference: string): {
  minimum?: number;
  maximum?: number;
  multipleOf?: number;
} {
  return collectRange(schemaAt(reference));
}

export function descOf(reference: string): string | undefined {
  const direct = resolvePointer(VL_SCHEMA, reference);
  if (direct?.description || direct?.title) {
    return direct.description ?? direct.title;
  }
  const node = schemaAt(reference);
  return node?.description ?? node?.title;
}

export function typeOf(reference: string): string | undefined {
  const node = schemaAt(reference);
  return typeof node?.type === "string" ? node.type : undefined;
}

interface FieldSpec {
  name: string;
  required: boolean;
  /** The schema node for this field, keeping its original `$ref`. */
  schema: JsonSchema;
  type?: string;
  types?: string[];
  enum?: string[];
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
}

function collectProps(
  node: JsonSchema | undefined,
  properties: Record<string, JsonSchema>,
  required: Set<string>,
  seen: Set<string>,
): void {
  if (!node) {
    return;
  }
  if (node.$ref) {
    if (seen.has(node.$ref)) {
      return;
    }
    seen.add(node.$ref);
    collectProps(resolvePointer(VL_SCHEMA, node.$ref), properties, required, seen);
    return;
  }
  for (const [name, property] of Object.entries(node.properties ?? {})) {
    properties[name] = property;
  }
  if (Array.isArray(node.required)) {
    for (const name of node.required) {
      if (typeof name === "string") {
        required.add(name);
      }
    }
  }
  for (const branch of node.allOf ?? []) {
    collectProps(branch, properties, required, seen);
  }
}

function collectTypes(
  node: JsonSchema | undefined,
  types: Set<string>,
  seen: Set<string>,
): void {
  if (!node) {
    return;
  }
  if (node.$ref) {
    if (seen.has(node.$ref)) {
      return;
    }
    seen.add(node.$ref);
    collectTypes(resolvePointer(VL_SCHEMA, node.$ref), types, seen);
    return;
  }
  if (typeof node.type === "string") {
    types.add(node.type);
  } else if (Array.isArray(node.type)) {
    for (const type of node.type) {
      if (typeof type === "string") {
        types.add(type);
      }
    }
  }
  for (const branch of node.anyOf ?? node.oneOf ?? []) {
    collectTypes(branch, types, seen);
  }
}

function describeField(
  name: string,
  propertySchema: JsonSchema,
  required: boolean,
): FieldSpec {
  const resolved = deref(VL_SCHEMA, propertySchema).schema ?? propertySchema;
  const field: FieldSpec = { name, required, schema: propertySchema };

  const types = new Set<string>();
  collectTypes(resolved, types, new Set());
  if (types.size === 1) {
    field.type = [...types][0];
  } else if (types.size > 1) {
    field.types = [...types];
  }

  const values = collectEnum(resolved);
  if (values.length > 0) {
    field.enum = values;
  }
  if (resolved.description) {
    field.description = resolved.description;
  }
  if (resolved.default !== undefined) {
    field.default = resolved.default;
  }
  const range = collectRange(resolved);
  if (range.minimum !== undefined) {
    field.minimum = range.minimum;
  }
  if (range.maximum !== undefined) {
    field.maximum = range.maximum;
  }
  return field;
}

/** List the properties of a schema object with their metadata. */
export function fieldsOf(reference: string): FieldSpec[] {
  const node = schemaAt(reference);
  if (!node) {
    return [];
  }

  const properties: Record<string, JsonSchema> = {};
  const required = new Set<string>();
  collectProps(node, properties, required, new Set());

  return Object.entries(properties).map(([name, propertySchema]) =>
    describeField(name, propertySchema, required.has(name)),
  );
}

function propertyAt(
  node: JsonSchema | undefined,
  name: string,
  seen: Set<string> = new Set(),
): JsonSchema | undefined {
  if (!node) {
    return undefined;
  }
  if (node.$ref) {
    if (seen.has(node.$ref)) {
      return undefined;
    }
    seen.add(node.$ref);
    return propertyAt(resolvePointer(VL_SCHEMA, node.$ref), name, seen);
  }
  if (node.properties?.[name]) {
    return node.properties[name];
  }
  for (const branch of node.allOf ?? []) {
    const found = propertyAt(branch, name, seen);
    if (found) {
      return found;
    }
  }
  for (const branch of [...(node.anyOf ?? []), ...(node.oneOf ?? [])]) {
    const found = propertyAt(branch, name, seen);
    if (found) {
      return found;
    }
  }
  return undefined;
}

/** Resolve a dotted property path and describe its leaf field. */
export function fieldAt(
  reference: string,
  path: string,
): FieldSpec | undefined {
  let property: JsonSchema | undefined = schemaAt(reference);
  let name = "";
  for (const part of path.split(".")) {
    name = part;
    property = propertyAt(property, part);
    if (!property) {
      return undefined;
    }
  }
  return property ? describeField(name, property, false) : undefined;
}
