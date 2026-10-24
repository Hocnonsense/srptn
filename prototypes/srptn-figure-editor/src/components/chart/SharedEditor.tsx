import type { ChartState } from "../../lib/chart/state/types";
import { ChannelShelf } from "./ChannelShelf";
import { TransformList } from "./TransformList";

export function SharedEditor({ state }: { state?: ChartState }) {
  return (
    <section className="panel shared-card">
      <div className="panel-heading">
        <h2>Shared</h2>
        <span className="muted">applies to every layer</span>
      </div>
      <TransformList scope="shared" state={state} />
      <ChannelShelf scope="shared" state={state} />
    </section>
  );
}
