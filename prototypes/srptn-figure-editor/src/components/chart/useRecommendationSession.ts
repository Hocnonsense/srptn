import { useCallback, useState } from "react";

import { buildSpec } from "../../lib/chart/engine/buildSpec";
import { validateSpec } from "../../lib/chart/engine/validate";
import { validateChartState } from "../../lib/chart/engine/validateState";
import type { TableSchema } from "../../lib/chart/schema/table-schema";
import type { ChartState } from "../../lib/chart/state/types";

interface RecommendationSessionState {
  open: boolean;
  baseline: ChartState | null;
  previewState: ChartState;
  error?: string;
  openRecommendations(): void;
  previewRecommendation(state: ChartState | null): void;
  applyRecommendation(state: ChartState): void;
  cancelRecommendations(): void;
}

export function useRecommendationSession({
  state,
  table,
  replaceState,
  specEditing,
}: {
  state: ChartState;
  table: TableSchema;
  replaceState: (state: ChartState) => void;
  specEditing: boolean;
}): RecommendationSessionState {
  const [open, setOpen] = useState(false);
  const [baseline, setBaseline] = useState<ChartState | null>(null);
  const [preview, setPreview] = useState<ChartState | null>(null);
  const [error, setError] = useState<string>();

  const openRecommendations = useCallback(() => {
    if (specEditing) {
      return;
    }
    setBaseline(state);
    setPreview(null);
    setError(undefined);
    setOpen(true);
  }, [specEditing, state]);

  const previewRecommendation = useCallback((next: ChartState | null) => {
    setError(undefined);
    setPreview(next);
  }, []);

  const applyRecommendation = useCallback(
    (next: ChartState) => {
      const spec = buildSpec(next, {
        includeData: true,
        rows: table.rows,
      });
      const issue = [
        ...validateChartState(next),
        ...validateSpec(spec),
      ].find((item) => item.severity === "error");
      if (issue) {
        setError(issue.message);
        return;
      }
      replaceState(next);
      setBaseline(next);
      setPreview(null);
      setError(undefined);
    },
    [replaceState, table.rows],
  );

  const cancelRecommendations = useCallback(() => {
    setOpen(false);
    setBaseline(null);
    setPreview(null);
    setError(undefined);
  }, []);

  return {
    open,
    baseline,
    previewState: open && preview ? preview : state,
    error,
    openRecommendations,
    previewRecommendation,
    applyRecommendation,
    cancelRecommendations,
  };
}
