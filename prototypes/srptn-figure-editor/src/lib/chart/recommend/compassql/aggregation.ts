/**
 * Adapted from CompassQL (University of Washington Interactive Data Lab),
 * BSD-3-Clause. See LICENSE in this directory.
 */
import type { RecommendationProfile } from "../profile";
import type { Candidate } from "../types";
import {
  activeDeriveKind,
  hasDerive,
  hasDeriveKind,
} from "../../engine/channelFn";
import {
  candidateEncoding,
  fieldOf,
  isAggregateCandidate,
  isDimensionState,
} from "./extendedType";

export function aggregationQuality(
  profile: RecommendationProfile,
  candidate: Candidate,
): number {
  const encoding = Object.values(candidateEncoding(candidate));
  if (isAggregateCandidate(candidate)) {
    const hasRawContinuous = encoding.some((state) => {
      if (typeof state.aggregate === "string") {
        return false;
      }
      if (state.type !== "quantitative" && state.type !== "temporal") {
        return false;
      }
      return !hasDerive(state);
    });
    if (hasRawContinuous) {
      return 0.1;
    }

    const hasDimension = encoding.some((state) =>
      isDimensionState(state, fieldOf(profile, state)),
    );
    if (hasDimension) {
      const hasCount = encoding.some(
        (state) => state.aggregate === "count",
      );
      const hasBin = encoding.some((state) =>
        hasDeriveKind(state, "bin"),
      );
      if (hasCount) {
        return 0.8;
      }
      if (hasBin) {
        return 0.7;
      }
      return 0.9;
    }
    return 0.3;
  }

  const hasMeasure = encoding.some((state) => {
    if (typeof state.aggregate === "string") {
      return true;
    }
    if (activeDeriveKind(state)) {
      return false;
    }
    return state.type === "quantitative" || state.type === "temporal";
  });
  return hasMeasure ? 1 : 0.2;
}
