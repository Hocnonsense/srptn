/**
 * Adapted from CompassQL (University of Washington Interactive Data Lab),
 * BSD-3-Clause. See LICENSE in this directory.
 */
import type { RecommendationProfile } from "../profile";
import type { Candidate } from "../types";

export function fieldOrderScore(
  profile: RecommendationProfile,
  candidate: Candidate,
): number {
  const indexOf = new Map(
    profile.fields.map((field, index) => [field.name, index]),
  );
  const count = Math.max(1, profile.fields.length);
  let base = 1;
  let total = 0;
  for (const field of candidate.fields) {
    const index = indexOf.get(field);
    if (index === undefined) {
      continue;
    }
    total -= index * base;
    base *= count;
  }
  return total;
}
