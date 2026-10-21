import type { ChannelState } from "../state/types";
import type { VegaType } from "../schema/table-schema";
import { DERIVE_SPECS, TIME_UNITS } from "./transforms";

interface ChannelFnParam {
  key: string;
  kind: "number" | "select";
  options?: readonly string[];
  placeholder?: string;
  min?: number;
  value: (state: ChannelState) => unknown;
  patch: (value: unknown) => Partial<ChannelState>;
}

const CHANNEL_FN_PARAMS: Record<string, ChannelFnParam[]> = {
  bin: [
    {
      key: "maxbins",
      kind: "number",
      placeholder: "maxbins",
      min: 2,
      value: (state) =>
        state.bin && typeof state.bin === "object"
          ? (state.bin as Record<string, unknown>).maxbins
          : undefined,
      patch: (value) => ({
        bin:
          value === undefined || value === ""
            ? true
            : { maxbins: Number(value) },
      }),
    },
  ],
  timeUnit: [
    {
      key: "timeUnit",
      kind: "select",
      options: TIME_UNITS,
      value: (state) => state.timeUnit,
      patch: (value) => ({ timeUnit: String(value) }),
    },
  ],
};

export function channelFnParams(kind: string): ChannelFnParam[] {
  return CHANNEL_FN_PARAMS[kind] ?? [];
}

export const ENCODING_DERIVE_KINDS = Object.keys(DERIVE_SPECS).filter(
  (kind) =>
    kind !== "calculate" &&
    DERIVE_SPECS[kind as keyof typeof DERIVE_SPECS].encoding,
);

type ChannelFnKind = "none" | "aggregate" | string;

export function channelFnAllowed(
  kind: string,
  fieldType: VegaType | undefined,
): boolean {
  if (kind === "bin") {
    return fieldType === "quantitative" || fieldType === "temporal";
  }
  if (kind === "timeUnit") {
    return fieldType === "temporal";
  }
  return true;
}

export function channelFnKind(state: ChannelState): ChannelFnKind {
  if (typeof state.aggregate === "string") {
    return "aggregate";
  }
  if (state.bin) {
    return "bin";
  }
  if (typeof state.timeUnit === "string") {
    return "timeUnit";
  }
  return "none";
}

export function channelFnPatch(
  kind: ChannelFnKind,
  value?: string,
): Partial<ChannelState> {
  return {
    aggregate: kind === "aggregate" ? value : undefined,
    bin: kind === "bin" ? true : undefined,
    timeUnit: kind === "timeUnit" ? (value ?? "year") : undefined,
  };
}
