export const SCORE_WEIGHTS = {
  effectiveness: 0.45,
  significance: 0.35,
  context: 0.1,
  parsimony: 0.1,
} as const;

export const CARDINALITY = {
  lowMax: 8,
  mediumMax: 20,
  idRatio: 0.9,
  idMinRows: 20,
  missingRatio: 0.8,
  overplotMarks: 200,
} as const;
