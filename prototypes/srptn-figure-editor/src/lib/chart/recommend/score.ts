import type { FieldProfile, RecommendationProfile } from "./profile";
import { pairSignificanceOf, significanceOf } from "./profile";
import type { Candidate, ScoreBreakdown } from "./types";
import { CARDINALITY, SCORE_WEIGHTS } from "./rules";
import { hasDerive, hasDeriveKind } from "../engine/channelFn";
import { compassScore } from "./compassql";

export function scoreCandidate(
  profile: RecommendationProfile,
  candidate: Candidate,
): ScoreBreakdown {
  const effectiveness = effectivenessScore(profile, candidate);
  const significance = significanceScore(profile, candidate);
  const context = 0.5;
  const parsimony = clamp01(
    1 - 0.05 * Math.max(0, candidate.fields.length - 1),
  );
  const total =
    effectiveness * SCORE_WEIGHTS.effectiveness +
    significance * SCORE_WEIGHTS.significance +
    context * SCORE_WEIGHTS.context +
    parsimony * SCORE_WEIGHTS.parsimony;

  return { effectiveness, significance, context, parsimony, total };
}

function effectivenessScore(
  profile: RecommendationProfile,
  candidate: Candidate,
): number {
  const compass = compassScore(profile, candidate);
  let score = clamp01(
    0.65 * normalizeCompass(compass.effectiveness) +
    0.35 * compass.aggregation,
  );
  const color = fieldFor(profile, candidate, "color");
  if (color) {
    if (color.distinctCount <= CARDINALITY.lowMax) {
      score += 0.04;
    } else if (color.distinctCount <= CARDINALITY.mediumMax) {
      score -= 0.04;
    } else {
      score -= 0.25;
    }
  }
  const marks = estimatedMarks(profile, candidate);
  if (marks > CARDINALITY.overplotMarks) {
    score -= Math.min(
      0.28,
      Math.log10(marks / CARDINALITY.overplotMarks) * 0.12,
    );
  }
  return clamp01(score);
}

function significanceScore(
  profile: RecommendationProfile,
  candidate: Candidate,
): number {
  const fields = candidate.fields;
  if (fields.length === 0) {
    return 0;
  }
  const columnAverage =
    fields.reduce(
      (sum, field) => sum + significanceOf(profile, field),
      0,
    ) / fields.length;

  const pairs: number[] = [];
  for (let left = 0; left < fields.length; left += 1) {
    for (let right = left + 1; right < fields.length; right += 1) {
      pairs.push(pairSignificanceOf(profile, fields[left], fields[right]));
    }
  }
  if (pairs.length === 0) {
    return clamp01(columnAverage);
  }
  return clamp01(
    0.7 * Math.max(...pairs) + 0.3 * columnAverage,
  );
}


function estimatedMarks(
  profile: RecommendationProfile,
  candidate: Candidate,
): number {
  const encoding = candidate.state.layers[0]?.encoding ?? {};
  const rawPosition = (state: typeof encoding[string] | undefined) =>
    Boolean(state?.field && !state.aggregate && !hasDerive(state));
  if (
    (candidate.mark === "point" ||
      candidate.mark === "circle" ||
      candidate.mark === "square") &&
    rawPosition(encoding.x) &&
    rawPosition(encoding.y)
  ) {
    return profile.n;
  }
  if (
    encoding.x &&
    hasDeriveKind(encoding.x, "bin") &&
    encoding.y?.aggregate === "count"
  ) {
    return Math.min(30, Math.max(2, Math.ceil(Math.sqrt(profile.n))));
  }
  const dimensions = candidate.fields
    .map((name) => profile.byName.get(name))
    .filter((field): field is FieldProfile => field?.role === "dimension");
  if (dimensions.length === 0) {
    return profile.n;
  }
  return dimensions.reduce(
    (product, field) => product * Math.max(1, field.distinctCount),
    1,
  );
}

function fieldFor(
  profile: RecommendationProfile,
  candidate: Candidate,
  channel: "x" | "y" | "color",
): FieldProfile | undefined {
  const name = candidate.channels[channel];
  return name ? profile.byName.get(name) : undefined;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function normalizeCompass(score: number): number {
  return 1 / (1 + Math.exp(-score / 3));
}
