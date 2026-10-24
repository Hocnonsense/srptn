import type { VegaType } from "../../schema/table-schema";
import type { ChannelState } from "../../state/types";
import { DERIVE_SPECS } from "../../engine/transforms";
import type { EncodingDeriveKind } from "../../engine/transforms";
import type { FieldProfile, RecommendationProfile } from "../profile";
import type { Candidate } from "../types";
import { activeDeriveKind } from "../../engine/channelFn";

export interface ExtendedType {
  type: VegaType;
  derive?: EncodingDeriveKind;
  domain: "continuous" | "discrete";
  key: boolean;
}

const TYPE_CODE: Record<VegaType, string> = {
  quantitative: "Q",
  temporal: "T",
  ordinal: "O",
  nominal: "N",
};

export function extendedTypeKey(value: ExtendedType): string {
  if (value.key) {
    return "key";
  }
  if (value.derive) {
    return `${value.derive}_${value.domain === "discrete" ? "O" : TYPE_CODE[value.type]}`;
  }
  return TYPE_CODE[value.type];
}

export function channelExtendedType(
  state: ChannelState,
  field?: FieldProfile,
): ExtendedType {
  const type = state.type ?? field?.type ?? "nominal";
  if (!field && state.aggregate === "count") {
    return { type: "quantitative", domain: "continuous", key: false };
  }
  const derive = activeDeriveKind(state);
  if (derive) {
    const outputType = DERIVE_SPECS[derive].outputType ?? type;
    return {
      type: outputType,
      derive,
      domain:
        outputType === "quantitative"
          ? "continuous"
          : outputType === "temporal"
            ? hasDiscreteScale(state) ? "discrete" : "continuous"
            : "discrete",
      key: false,
    };
  }
  return {
    type,
    domain:
      type === "quantitative" || type === "temporal"
        ? "continuous"
        : "discrete",
    key: Boolean(field?.isId),
  };
}

export function isDimensionState(
  state: ChannelState,
  field?: FieldProfile,
): boolean {
  if (!field) {
    return false;
  }
  if (activeDeriveKind(state)) {
    return true;
  }
  return state.type === "nominal" || state.type === "ordinal";
}

export function candidateEncoding(
  candidate: Candidate,
): Record<string, ChannelState> {
  return candidate.state.layers[0]?.encoding ?? {};
}

export function isAggregateCandidate(candidate: Candidate): boolean {
  return Object.values(candidateEncoding(candidate)).some(
    (state) => typeof state.aggregate === "string",
  );
}

export function fieldOf(
  profile: RecommendationProfile,
  state: ChannelState,
): FieldProfile | undefined {
  return typeof state.field === "string"
    ? profile.byName.get(state.field)
    : undefined;
}

function hasDiscreteScale(state: ChannelState): boolean {
  const type = state.scale?.type;
  return type === "band" || type === "point" || type === "ordinal";
}
