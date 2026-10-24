/**
 * Adapted from CompassQL (University of Washington Interactive Data Lab),
 * BSD-3-Clause. See LICENSE in this directory.
 */
import type { ChannelState } from "../../state/types";
import type { RecommendationProfile } from "../profile";
import type { Candidate } from "../types";
import {
  candidateEncoding,
  channelExtendedType,
  extendedTypeKey,
  fieldOf,
  isAggregateCandidate,
  isDimensionState,
  type ExtendedType,
} from "./extendedType";

export interface FeatureScore {
  type: string;
  feature: string;
  score: number;
}

export interface EffectivenessScore {
  score: number;
  features: FeatureScore[];
}

const TERRIBLE = -10;

export function compassEffectiveness(
  profile: RecommendationProfile,
  candidate: Candidate,
): EffectivenessScore {
  const features = [
    ...axisFeatures(candidate),
    ...dimensionFeatures(profile, candidate),
    ...facetFeatures(candidate),
    ...markFeatures(profile, candidate),
    ...sizeChannelFeatures(candidate),
    ...typeChannelFeatures(profile, candidate),
  ];
  return {
    score: features.reduce((sum, feature) => sum + feature.score, 0),
    features,
  };
}

function axisFeatures(candidate: Candidate): FeatureScore[] {
  const features: FeatureScore[] = [];
  for (const [channel, state] of Object.entries(candidateEncoding(candidate))) {
    if (channel !== "x" && channel !== "y") {
      continue;
    }
    const type = channelExtendedType(state);
    const key = extendedTypeKey(type);
    if (
      (channel === "y" && prefersX(type)) ||
      (channel === "x" && prefersY(type))
    ) {
      features.push({
        type: "Axis",
        feature: `${key}_${channel}`,
        score: -0.01,
      });
    }
  }
  return features;
}

function prefersX(type: ExtendedType): boolean {
  return type.derive !== undefined || type.type === "temporal";
}

function prefersY(type: ExtendedType): boolean {
  return (
    type.derive === undefined &&
    (type.type === "ordinal" || type.type === "nominal")
  );
}

function dimensionFeatures(
  profile: RecommendationProfile,
  candidate: Candidate,
): FeatureScore[] {
  if (!isAggregateCandidate(candidate)) {
    return [];
  }
  const scores: Record<string, number> = {
    x: 0,
    y: 0,
    row: -2,
    column: -2,
    color: 0,
    opacity: 0,
    size: 0,
    shape: 0,
  };
  let best: FeatureScore = {
    type: "Dimension",
    feature: "No Dimension",
    score: -5,
  };
  for (const [channel, state] of Object.entries(candidateEncoding(candidate))) {
    const field = fieldOf(profile, state);
    if (!isDimensionState(state, field)) {
      continue;
    }
    const score = scores[channel];
    if (score !== undefined && score > best.score) {
      best = { type: "Dimension", feature: channel, score };
    }
  }
  return [best];
}

function facetFeatures(candidate: Candidate): FeatureScore[] {
  const encoding = candidateEncoding(candidate);
  const features: FeatureScore[] = [];
  if (encoding.column) {
    features.push({ type: "Facet", feature: "column", score: -0.01 });
  }
  if (encoding.row) {
    features.push({ type: "Facet", feature: "row", score: 0 });
  }
  return features;
}

function markFeatures(
  profile: RecommendationProfile,
  candidate: Candidate,
): FeatureScore[] {
  const encoding = candidateEncoding(candidate);
  const x = encoding.x;
  const y = encoding.y;
  const xType = x
    ? extendedTypeKey(channelExtendedType(x, fieldOf(profile, x)))
    : undefined;
  const yType = y
    ? extendedTypeKey(channelExtendedType(y, fieldOf(profile, y)))
    : undefined;
  const mark = candidate.mark === "circle" || candidate.mark === "square"
    ? "point"
    : candidate.mark;
  const feature = `${xType ?? "-"}_${yType ?? "-"}_${!isAggregateCandidate(candidate)}_${mark}`;
  const score = MARK_SCORES[feature];
  return score === undefined
    ? []
    : [{ type: "Mark", feature, score }];
}

function sizeChannelFeatures(candidate: Candidate): FeatureScore[] {
  if (!("size" in candidateEncoding(candidate))) {
    return [];
  }
  const feature = `${candidate.mark}_size`;
  const score = feature === "bar_size" || feature === "tick_size" ? -2 : undefined;
  return score === undefined
    ? []
    : [{ type: "SizeChannel", feature, score }];
}

function typeChannelFeatures(
  profile: RecommendationProfile,
  candidate: Candidate,
): FeatureScore[] {
  const bestByField = new Map<string, FeatureScore>();
  for (const [channel, state] of Object.entries(candidateEncoding(candidate))) {
    const field = fieldOf(profile, state);
    if (!field) {
      continue;
    }
    const type = extendedTypeKey(channelExtendedType(state, field));
    const score = TYPE_CHANNEL_SCORES[`${type}_${channel}`];
    if (score === undefined) {
      continue;
    }
    const current = bestByField.get(field.name);
    if (!current || score > current.score) {
      bestByField.set(field.name, {
        type: "TypeChannel",
        feature: `${type}_${channel}`,
        score,
      });
    }
  }
  return [...bestByField.values()];
}

const CONTINUOUS_TYPE_CHANNEL_SCORE: Record<string, number> = {
  x: 0,
  y: 0,
  size: -0.575,
  color: -0.725,
  text: -2,
  opacity: -3,
  shape: TERRIBLE,
  row: TERRIBLE,
  column: TERRIBLE,
  detail: 2 * TERRIBLE,
};

const ORDERED_TYPE_CHANNEL_SCORE: Record<string, number> = {
  ...CONTINUOUS_TYPE_CHANNEL_SCORE,
  row: -0.75,
  column: -0.75,
  shape: -3.1,
  text: -3.2,
  detail: -4,
};

const NOMINAL_TYPE_CHANNEL_SCORE: Record<string, number> = {
  x: 0,
  y: 0,
  color: -0.6,
  shape: -0.65,
  row: -0.7,
  column: -0.7,
  text: -0.8,
  detail: -2,
  size: -3,
  opacity: -3.1,
};

const TYPE_CHANNEL_SCORES: Record<string, number> = (() => {
  const scores: Record<string, number> = {};
  for (const type of ["Q", "T", "timeUnit_T"]) {
    for (const [channel, score] of Object.entries(CONTINUOUS_TYPE_CHANNEL_SCORE)) {
      scores[`${type}_${channel}`] = score;
    }
  }
  for (const type of ["bin_Q", "timeUnit_O", "O"]) {
    for (const [channel, score] of Object.entries(ORDERED_TYPE_CHANNEL_SCORE)) {
      scores[`${type}_${channel}`] = score;
    }
  }
  for (const [channel, score] of Object.entries(NOMINAL_TYPE_CHANNEL_SCORE)) {
    scores[`N_${channel}`] = score;
    scores[`key_${channel}`] =
      channel === "x" || channel === "y" || channel === "detail"
        ? -1
        : score - 2;
  }
  return scores;
})();

const MEASURES = ["Q", "T"];
const DISCRETE = ["bin_Q", "timeUnit_O", "O", "N", "key"];
const DISCRETE_OR_NONE = [...DISCRETE, "-"];

const MARK_SCORES: Record<string, number> = (() => {
  const scores: Record<string, number> = {};
  const set = (
    xType: string,
    yType: string,
    occluded: boolean,
    mark: string,
    score: number,
  ) => {
    scores[`${xType}_${yType}_${occluded}_${mark}`] = score;
  };
  const addBoth = (
    xType: string,
    yType: string,
    occluded: boolean,
    table: Record<string, number>,
  ) => {
    for (const [mark, score] of Object.entries(table)) {
      set(xType, yType, occluded, mark, score);
      set(yType, xType, occluded, mark, score);
    }
  };

  for (const xType of MEASURES) {
    for (const yType of MEASURES) {
      const occluded = {
        point: 0,
        text: -0.2,
        tick: -0.5,
        rect: -1,
        bar: -2,
        line: -2,
        area: -2,
        rule: -2.5,
      };
      for (const [mark, score] of Object.entries(occluded)) {
        set(xType, yType, true, mark, score);
      }
      const noOcclusion = {
        point: 0,
        text: -0.2,
        tick: -0.5,
        bar: -2,
        line: -2,
        area: -2,
        rule: -2.5,
      };
      for (const [mark, score] of Object.entries(noOcclusion)) {
        set(xType, yType, false, mark, score);
      }
    }
  }

  for (const xType of MEASURES) {
    const occludedDimensionMeasure = {
      tick: 0,
      point: -0.2,
      text: -0.5,
      bar: -2,
      line: -2,
      area: -2,
      rule: -2.5,
    };
    for (const yType of DISCRETE_OR_NONE) {
      addBoth(xType, yType, true, occludedDimensionMeasure);
    }

    const occludedTemporal = {
      point: 0,
      text: -0.5,
      tick: -1,
      bar: -2,
      line: -2,
      area: -2,
      rule: -2.5,
    };
    addBoth(xType, "timeUnit_T", true, occludedTemporal);

    const noOccludedQxN = {
      bar: 0,
      point: -0.2,
      tick: -0.25,
      text: -0.3,
      line: -2,
      area: -2,
      rule: -2.5,
    };
    for (const yType of ["-", "N", "O", "key"]) {
      addBoth(xType, yType, false, noOccludedQxN);
    }

    const noOccludedQxBin = {
      bar: 0,
      point: -0.2,
      tick: -0.25,
      text: -0.3,
      line: -0.5,
      area: -0.5,
      rule: -2.5,
    };
    addBoth(xType, "bin_Q", false, noOccludedQxBin);

    const noOccludedQxTime = {
      line: 0,
      area: -0.1,
      bar: -0.2,
      point: -0.3,
      tick: -0.35,
      text: -0.4,
      rule: -2.5,
    };
    addBoth(xType, "timeUnit_T", false, noOccludedQxTime);
    addBoth(xType, "timeUnit_O", false, noOccludedQxTime);
  }

  for (const yType of ["timeUnit_T"]) {
    const ttMark = {
      point: 0,
      rect: -0.1,
      text: -0.5,
      tick: -1,
      bar: -2,
      line: -2,
      area: -2,
      rule: -2.5,
    };
    for (const [mark, score] of Object.entries(ttMark)) {
      set("timeUnit_T", yType, true, mark, score);
      set("timeUnit_T", yType, false, mark, score);
    }
  }

  const tdMark = {
    tick: 0,
    point: -0.2,
    text: -0.5,
    rect: -1,
    bar: -2,
    line: -2,
    area: -2,
    rule: -2.5,
  };
  for (const yType of DISCRETE_OR_NONE) {
    for (const occluded of [true, false]) {
      for (const [mark, score] of Object.entries(tdMark)) {
        set("timeUnit_T", yType, occluded, mark, score);
        set(yType, "timeUnit_T", occluded, mark, score);
      }
    }
  }

  const ddMark = {
    point: 0,
    rect: 0,
    text: -0.1,
    tick: -1,
    bar: -2,
    line: -2,
    area: -2,
    rule: -2.5,
  };
  for (const xType of DISCRETE_OR_NONE) {
    for (const yType of DISCRETE_OR_NONE) {
      for (const occluded of [true, false]) {
        for (const [mark, score] of Object.entries(ddMark)) {
          set(xType, yType, occluded, mark, score);
        }
      }
    }
  }

  return scores;
})();
