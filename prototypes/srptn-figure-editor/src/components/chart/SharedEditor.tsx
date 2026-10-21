import { ChannelShelf } from "./ChannelShelf";
import { TransformList } from "./TransformList";

export function SharedEditor() {
  return (
    <section className="panel shared-card">
      <div className="panel-heading">
        <h2>Shared</h2>
        <span className="muted">applies to every layer</span>
      </div>
      <TransformList scope="shared" />
      <ChannelShelf scope="shared" />
    </section>
  );
}
