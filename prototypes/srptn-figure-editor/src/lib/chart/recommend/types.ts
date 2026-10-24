import type { ChartState } from "../state/types";

export type RecommendChannel = "x" | "y" | "color";

export type FieldRole = "measure" | "dimension" | "time" | "count";

export type CardinalityBand =
  | "constant"
  | "binary"
  | "low"
  | "medium"
  | "high";

export type SlotCardinality = "low" | "lowOrMedium" | "medium" | "any";

export type PatchOp =
  | { op: "set"; path: (string | number)[]; value: unknown }
  | { op: "remove"; path: (string | number)[] };

export interface ScoreBreakdown {
  effectiveness: number;
  significance: number;
  context: number;
  parsimony: number;
  total: number;
}

export interface Candidate {
  state: ChartState;
  fields: string[];
  channels: Partial<Record<RecommendChannel, string>>;
  mark: string;
}

export type RecommendationCategory =
  | "quantitative"
  | "categorical"
  | "temporal"
  | "encoding"
  | "summary"
  | "refinement"
  | "replacement";

export interface Recommendation {
  id: string;
  category: RecommendationCategory;
  title: string;
  description: string;
  state: ChartState;
  patch: PatchOp[];
  score: number;
}
