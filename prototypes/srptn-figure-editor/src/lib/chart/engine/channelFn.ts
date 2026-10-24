import type { ChannelState } from "../state/types";
import type { VegaType } from "../schema/table-schema";
import { aggregateName } from "./aggregate";
import type { DeriveControl, EncodingDeriveKind } from "./transforms";
import {
  DERIVE_SPECS,
  createDerivedTransform,
  deriveControls,
  derivedName,
  makeTransform,
  readTransform,
  withTransformMetadata,
} from "./transforms";

interface ChannelFnParam extends DeriveControl {
  value: (state: ChannelState) => unknown;
  patch: (value: unknown) => Partial<ChannelState>;
}

export const ENCODING_DERIVE_KINDS = (
  Object.keys(DERIVE_SPECS) as (keyof typeof DERIVE_SPECS)[]
).filter(
  (kind) =>
    kind !== "calculate" && DERIVE_SPECS[kind].encoding,
) as EncodingDeriveKind[];

type ChannelFnKind = "none" | "aggregate" | string;

export function channelFnParams(kind: string): ChannelFnParam[] {
  const derive = channelDerive(kind);
  if (!derive?.encoding || !derive.channelKey) {
    return [];
  }
  return deriveControls(kind as keyof typeof DERIVE_SPECS).map(
    (control): ChannelFnParam => ({
      ...control,
      value: (state: ChannelState): unknown => {
        const derived = channelDeriveState(kind, state) as
          | Record<string, unknown>
          | undefined;
        return derived?.[control.key];
      },
      patch: (next: unknown): Partial<ChannelState> => {
        const transform = makeTransform(
          kind as keyof typeof DERIVE_SPECS,
          { [control.key]: next } as never,
        );
        return {
          [derive.channelKey as string]: transform[derive.channelKey as string],
        } as Partial<ChannelState>;
      },
    }),
  );
}

export function channelFnAllowed(
  kind: string,
  fieldType: VegaType | undefined,
): boolean {
  const derive = channelDerive(kind);
  if (!derive?.sourceTypes) {
    return true;
  }
  return fieldType !== undefined && derive.sourceTypes.includes(fieldType);
}

export function channelFnKind(state: ChannelState): ChannelFnKind {
  if (typeof state.aggregate === "string") {
    return state.aggregate;
  }
  for (const kind of ENCODING_DERIVE_KINDS) {
    if (channelDeriveState(kind, state) !== undefined) {
      return kind;
    }
  }
  return "none";
}

export function channelFnPatch(
  kind: ChannelFnKind,
  value?: string,
): Partial<ChannelState> {
  const patch: Record<string, unknown> = { aggregate: undefined };
  for (const deriveKind of ENCODING_DERIVE_KINDS) {
    const key = channelDerive(deriveKind)?.channelKey;
    if (key) {
      patch[key] = undefined;
    }
  }
  if (kind === "aggregate") {
    patch.aggregate = value;
    return patch as Partial<ChannelState>;
  }
  const derive = channelDerive(kind);
  if (!derive?.encoding || !derive.channelKey) {
    return patch as Partial<ChannelState>;
  }
  const transform = createDerivedTransform(
    kind as keyof typeof DERIVE_SPECS,
    { field: "", quantitativeField: "", temporalField: "" },
  );
  patch[derive.channelKey] = transform[derive.channelKey];
  return patch as Partial<ChannelState>;
}

export function channelFnLabel(state: ChannelState): string {
  const field =
    typeof state.field === "string" && state.field ? state.field : undefined;
  if (typeof state.aggregate === "string") {
    return aggregateName(state.aggregate, field);
  }
  for (const kind of ENCODING_DERIVE_KINDS) {
    const derived = channelDeriveState(kind, state);
    if (derived !== undefined) {
      return derivedName(
        kind as keyof typeof DERIVE_SPECS,
        derived as never,
      );
    }
  }
  return field ?? "—";
}

interface ChannelDerive {
  encoding?: boolean;
  sourceTypes?: readonly VegaType[];
  channelKey?: keyof ChannelState;
}

function channelDerive(kind: string): ChannelDerive | undefined {
  if (!Object.hasOwn(DERIVE_SPECS, kind)) {
    return undefined;
  }
  return DERIVE_SPECS[
    kind as keyof typeof DERIVE_SPECS
  ] as unknown as ChannelDerive;
}

function channelDeriveState(
  kind: string,
  state: ChannelState,
): unknown {
  const derive = channelDerive(kind);
  if (!derive?.channelKey) {
    return undefined;
  }
  const value = state[derive.channelKey];
  if (value === undefined || value === null || value === false) {
    return undefined;
  }
  const field =
    typeof state.field === "string" && state.field ? state.field : undefined;
  if (!field) {
    return undefined;
  }
  return readTransform(
    kind as keyof typeof DERIVE_SPECS,
    withTransformMetadata({
      as: "channel",
      field,
      [derive.channelKey]: value,
    }),
  );
}

export function activeDeriveKind(
  state: ChannelState,
): EncodingDeriveKind | undefined {
  return ENCODING_DERIVE_KINDS.find((kind) =>
    hasDeriveKind(state, kind),
  );
}

export function hasDerive(state: ChannelState): boolean {
  return activeDeriveKind(state) !== undefined;
}

export function hasDeriveKind(
  state: ChannelState,
  kind: EncodingDeriveKind,
): boolean {
  const channelKey = DERIVE_SPECS[kind].channelKey;
  return channelKey ? Boolean(state[channelKey]) : false;
}
