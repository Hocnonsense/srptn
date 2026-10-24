import type { RecommendationProfile } from "../profile";
import type { Candidate } from "../types";
import { aggregationQuality } from "./aggregation";
import { compassEffectiveness, type FeatureScore } from "./effectiveness";
import { fieldOrderScore } from "./fieldOrder";

export { aggregationQuality } from "./aggregation";
export {
  compassEffectiveness,
  type EffectivenessScore,
  type FeatureScore,
} from "./effectiveness";
export {
  candidateEncoding,
  channelExtendedType,
  extendedTypeKey,
  fieldOf,
  isAggregateCandidate,
  isDimensionState,
  type ExtendedType,
} from "./extendedType";
export { fieldOrderScore } from "./fieldOrder";

export interface CompassScore {
  effectiveness: number;
  aggregation: number;
  fieldOrder: number;
  features: FeatureScore[];
}

export function compassScore(
  profile: RecommendationProfile,
  candidate: Candidate,
): CompassScore {
  const effectiveness = compassEffectiveness(profile, candidate);
  return {
    effectiveness: effectiveness.score,
    aggregation: aggregationQuality(profile, candidate),
    fieldOrder: fieldOrderScore(profile, candidate),
    features: effectiveness.features,
  };
}
