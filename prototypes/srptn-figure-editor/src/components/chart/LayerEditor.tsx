import { ChannelShelf } from "./ChannelShelf";
import { LayerList } from "./LayerList";
import { TransformList } from "./TransformList";

export function LayerEditor() {
  return (
    <section className="panel layer-card">
      <LayerList />
      <TransformList scope="layer" />
      <ChannelShelf scope="layer" />
    </section>
  );
}
