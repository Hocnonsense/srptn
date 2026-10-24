import type { ChartState } from "../../lib/chart/state/types";
import { ChannelShelf } from "./ChannelShelf";
import { LayerList } from "./LayerList";
import { TransformList } from "./TransformList";

export function LayerEditor({ state }: { state?: ChartState }) {
  return (
    <section className="panel layer-card">
      <LayerList state={state} />
      <TransformList scope="layer" state={state} />
      <ChannelShelf scope="layer" state={state} />
    </section>
  );
}
