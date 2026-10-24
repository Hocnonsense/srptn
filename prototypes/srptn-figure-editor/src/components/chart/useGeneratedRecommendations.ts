import { useEffect, useRef, useState } from "react";

import GenerateWorker from "../../lib/chart/recommend/generate.worker?worker&inline";
import type { Recommendation } from "../../lib/chart/recommend/types";
import type {
  RecommendationWorkerRequest,
  RecommendationWorkerResponse,
} from "../../lib/chart/recommend/worker";
import type { TableSchema } from "../../lib/chart/schema/table-schema";
import type { ChartState } from "../../lib/chart/state/types";

export interface GeneratedRecommendations {
  recommendations: Recommendation[];
  loading: boolean;
  error?: string;
}

export function useGeneratedRecommendations({
  table,
  state,
  enabled,
}: {
  table: TableSchema;
  state: ChartState | null;
  enabled: boolean;
}): GeneratedRecommendations {
  const workerRef = useRef<Worker | null>(null);
  const requestRef = useRef("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>(
    [],
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!enabled) {
      workerRef.current = null;
      requestRef.current = "";
      setRecommendations([]);
      setLoading(false);
      setError(undefined);
      return;
    }
    let worker: Worker;
    try {
      worker = new GenerateWorker();
    } catch (workerError) {
      setError(
        workerError instanceof Error
          ? workerError.message
          : "Recommendation worker could not start.",
      );
      setLoading(false);
      return;
    }
    workerRef.current = worker;
    requestRef.current = "";
    setRecommendations([]);
    setLoading(true);
    setError(undefined);
    worker.onerror = (event) => {
      setError(event.message || "Recommendation worker failed.");
    };
    worker.onmessage = (
      event: MessageEvent<RecommendationWorkerResponse>,
    ) => {
      const message = event.data;
      if (message.type === "error") {
        if (!message.requestId || message.requestId === requestRef.current) {
          setError(message.message);
          setLoading(false);
        }
        return;
      }
      if (
        message.type !== "result" ||
        message.requestId !== requestRef.current
      ) {
        return;
      }
      setRecommendations(message.recommendations);
      setLoading(false);
    };
    worker.postMessage({ type: "load", table } satisfies RecommendationWorkerRequest);
    return () => {
      worker.postMessage({ type: "dispose" } satisfies RecommendationWorkerRequest);
      worker.terminate();
      workerRef.current = null;
    };
  }, [enabled, table]);

  useEffect(() => {
    if (!enabled || !state || !workerRef.current) {
      return;
    }
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    requestRef.current = requestId;
    setLoading(true);
    setError(undefined);
    workerRef.current.postMessage({
      type: "generate",
      requestId,
      state,
    } satisfies RecommendationWorkerRequest);
  }, [enabled, state, table]);

  return { recommendations, loading, error };
}
