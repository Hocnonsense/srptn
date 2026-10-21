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
import { SharedEditor } from "./chart/SharedEditor";
import { Preview } from "./chart/Preview";
import { SpecEditor } from "./chart/SpecEditor";
import { ThemePanel } from "./chart/ThemePanel";

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

  const spec = useMemo(
    () => buildSpec(state, { includeData: true, rows: table.rows }),
    [state, table.rows],
  );
  const saveSpec = useMemo(
    () => buildSpec(state, { includeData: false }),
    [state],
  );
  const issues = useMemo(
    () => [...validateChartState(state), ...validateSpec(spec)],
    [state, spec],
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
            <fieldset className="editor-fields" disabled={specEditing}>
              <SharedEditor />
              <LayerEditor />
              <ThemePanel />
              <AdvancedFields state={state} onApply={replaceState} />
            </fieldset>
          </section>

          <SpecEditor
            spec={saveSpec}
            exportSpec={spec}
            onApply={replaceState}
            onEditingChange={setSpecEditing}
          />
        </div>
        <Preview spec={spec} issues={issues} />

      </main>
    </div>
  );
}
