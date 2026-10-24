import { useMemo, useState } from "react";
import type { StoreApi } from "zustand/vanilla";

import "./chart/base.css";
import "./App.css";
import { buildSpec } from "../lib/chart/engine/buildSpec";
import { validateSpec } from "../lib/chart/engine/validate";
import { validateChartState } from "../lib/chart/engine/validateState";
import {
  ChartStoreContext,
  useChartStore,
  type ChartStore,
} from "../lib/chart/state/chart-store";
import { AdvancedFields } from "./chart/AdvancedFields";
import { DataPanel } from "./chart/DataPanel";
import { LayerEditor } from "./chart/LayerEditor";
import { RecommendPanel } from "./chart/RecommendPanel";
import { SharedEditor } from "./chart/SharedEditor";
import { Preview } from "./chart/Preview";
import { SpecEditor } from "./chart/SpecEditor";
import { ThemePanel } from "./chart/ThemePanel";
import { useRecommendationSession } from "./chart/useRecommendationSession";

export function App({ store }: { store: StoreApi<ChartStore> }) {
  return (
    <ChartStoreContext.Provider value={store}>
      <Editor />
    </ChartStoreContext.Provider>
  );
}

function Editor() {
  const state = useChartStore((store) => store.state);
  const table = useChartStore((store) => store.table);
  const reset = useChartStore((store) => store.reset);
  const replaceState = useChartStore((store) => store.replaceState);
  const [specEditing, setSpecEditing] = useState(false);
  const recommendation = useRecommendationSession({
    state,
    table,
    replaceState,
    specEditing,
  });

  const spec = useMemo(
    () => buildSpec(state, { includeData: true, rows: table.rows }),
    [state, table.rows],
  );
  const saveSpec = useMemo(
    () => buildSpec(state, { includeData: false }),
    [state],
  );
  const previewState = recommendation.previewState;
  const displayState = recommendation.open ? recommendation.previewState : undefined;
  const previewSpec = useMemo(
    () =>
      buildSpec(previewState, { includeData: true, rows: table.rows }),
    [previewState, table.rows],
  );
  const previewIssues = useMemo(
    () => [
      ...validateChartState(previewState),
      ...validateSpec(previewSpec),
    ],
    [previewState, previewSpec],
  );

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>SRPTN Figure Editor</h1>
          {/* <p>Schema-driven Vega-Lite mapping prototype · Data → Editor (Shared + Layer) → Save spec → Preview</p> */}
        </div>
        <button type="button" onClick={reset}>
          Reset
        </button>
      </header>

      <main className="layout">
        <div className="column">
          <DataPanel table={table} />

          <section className="panel editor-card">
            <fieldset
              className="editor-fields"
              disabled={specEditing || recommendation.open}
            >
              <SharedEditor state={displayState} />
              <LayerEditor state={displayState} />
              <ThemePanel />
              <AdvancedFields state={state} onApply={replaceState} />
            </fieldset>
          </section>

          <SpecEditor
            spec={saveSpec}
            exportSpec={spec}
            onApply={replaceState}
            onEditingChange={setSpecEditing}
            disabled={recommendation.open}
          />
        </div>
        <div
          className={`preview-slot ${recommendation.open ? "is-reserved" : ""}`}
        >
          <Preview spec={previewSpec} issues={previewIssues} />
        </div>
        <RecommendPanel
          table={table}
          baseline={recommendation.baseline}
          open={recommendation.open}
          specEditing={specEditing}
          error={recommendation.error}
          onOpen={recommendation.openRecommendations}
          onPreview={recommendation.previewRecommendation}
          onApply={recommendation.applyRecommendation}
          onCancel={recommendation.cancelRecommendations}
        />
      </main>
    </div>
  );
}
