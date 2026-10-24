import { enumOf } from "../../lib/chart/schema/vl-schema";
import { useChartStore } from "../../lib/chart/state/chart-store";
import {
  clampLayerIndex,
  type ChartState,
} from "../../lib/chart/state/types";

const MARKS = enumOf("#/definitions/Mark");

export function LayerList({ state: override }: { state?: ChartState }) {
  const storeState = useChartStore((store) => store.state);
  const storeActiveLayerIndex = useChartStore(
    (store) => store.activeLayerIndex,
  );
  const state = override ?? storeState;
  const activeLayerIndex = clampLayerIndex(state, storeActiveLayerIndex);
  const setActiveLayer = useChartStore((store) => store.setActiveLayer);
  const setMark = useChartStore((store) => store.setMark);
  const addLayer = useChartStore((store) => store.addLayer);
  const removeLayer = useChartStore((store) => store.removeLayer);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Layers</h2>
        <span className="muted">effect in the mark layer</span>
      </div>
      <div className="chip-row">
        {state.layers.map((layer, index) =>
          index === activeLayerIndex ? (
            <select
              key={index}
              className="chip active"
              value={layer.mark}
              title="Mark"
              onChange={(event) => {
                if (event.target.value) {
                  setMark(event.target.value);
                } else {
                  removeLayer(index);
                }
              }}
            >
              <option value="">—</option>
              {MARKS.map((mark) => (
                <option key={mark} value={mark}>
                  {mark}
                </option>
              ))}
            </select>
          ) : (
            <button
              type="button"
              key={index}
              className="chip"
              onClick={() => setActiveLayer(index)}
            >
              <span >{layer.mark}</span>
            </button>
          ),
        )}
        <button
          type="button"
          className="icon-button"
          title="Add new layer"
          onClick={() => addLayer()}
        > + </button>
      </div>
    </section>
  );
}
