import type { TableSchema } from "../schema/table-schema";
import type { ChartState } from "../state/types";
import type { Recommendation } from "./types";

export type RecommendationWorkerRequest =
  | { type: "load"; table: TableSchema }
  | { type: "generate"; requestId: string; state: ChartState }
  | { type: "dispose" };

export type RecommendationWorkerResponse =
  | { type: "loaded" }
  | {
    type: "result";
    requestId: string;
    recommendations: Recommendation[];
  }
  | { type: "error"; requestId?: string; message: string };
