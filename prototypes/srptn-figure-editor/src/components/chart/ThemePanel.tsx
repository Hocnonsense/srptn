import { useChartStore } from "../../lib/chart/state/chart-store";
import type { ChannelState, Scope } from "../../lib/chart/state/types";
import { colorSchemes, scaleTypes } from "../../lib/chart/metamodel/rules";
import "./ThemePanel.css";

const SCALE_CHANNELS = ["x", "y"] as const;
const COLOR_CHANNELS = ["color", "fill", "stroke"] as const;

export function ThemePanel() {
  const state = useChartStore((store) => store.state);
  const activeLayerIndex = useChartStore((store) => store.activeLayerIndex);
  const setChannel = useChartStore((store) => store.setChannel);
  const setState = useChartStore((store) => store.patchState);
  const layer = state.layers[activeLayerIndex] ?? state.layers[0];

  const scaleChannels = new Map<string, { state: ChannelState; scope: Scope }>();
  for (const [channel, channelState] of Object.entries(
    state.shared.encoding,
  )) {
    if (channelState?.field) {
      scaleChannels.set(channel, { state: channelState, scope: "shared" });
    }
  }
  for (const [channel, channelState] of Object.entries(layer.encoding)) {
    if (channelState?.field) {
      scaleChannels.set(channel, { state: channelState, scope: "layer" });
    }
  }

  return (
    <details className="panel theme-panel">
      <summary className="panel-heading">
        <span>Theme & scale</span>
        <span className="muted">global title/size/scales</span>
      </summary>
      <div className="theme-grid">
        <label className="control-row">
          <span>Title</span>
          <input
            value={state.title ?? ""}
            onChange={(event) => setState({ title: event.target.value })}
          />
        </label>
        <label className="control-row">
          <span>Width</span>
          <input
            type="number"
            min={0}
            value={state.width ?? ""}
            onChange={(event) =>
              setState({
                width:
                  event.target.value === ""
                    ? undefined
                    : Number(event.target.value),
              })
            }
          />
        </label>
        <label className="control-row">
          <span>Height</span>
          <input
            type="number"
            min={0}
            value={state.height ?? ""}
            onChange={(event) =>
              setState({
                height:
                  event.target.value === ""
                    ? undefined
                    : Number(event.target.value),
              })
            }
          />
        </label>
        <label className="control-row">
          <span>Background</span>
          <input
            value={state.background ?? ""}
            onChange={(event) =>
              setState({ background: event.target.value || undefined })
            }
          />
        </label>
      </div>

      {scaleChannels.size > 0 && (
        <div className="theme-section">
          {[...scaleChannels].map(([channel, { state: channelState, scope }]) => {
            const fieldType = channelState.type;
            if (!fieldType) {
              return null;
            }
            const types = scaleTypes(channel as never, fieldType);
            const schemes = (COLOR_CHANNELS as readonly string[]).includes(
              channel,
            )
              ? colorSchemes(fieldType)
              : [];

            if (
              (SCALE_CHANNELS as readonly string[]).includes(channel) &&
              types.length > 0
            ) {
              return (
                <label className="control-row" key={channel}>
                  <span>{channel} scale</span>
                  <select
                    value={String(channelState.scale?.type ?? "")}
                    onChange={(event) => {
                      const scale = {
                        ...(channelState.scale ?? {}),
                        type: event.target.value || undefined,
                      };
                      if (!event.target.value) {
                        delete scale.type;
                      }
                      setChannel(channel, { scale }, scope);
                    }}
                  >
                    <option value="">auto</option>
                    {types.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </label>
              );
            }

            if (schemes.length > 0) {
              return (
                <label className="control-row" key={channel}>
                  <span>{channel} scheme</span>
                  <select
                    value={String(channelState.scale?.scheme ?? "")}
                    onChange={(event) => {
                      const scale = {
                        ...(channelState.scale ?? {}),
                        scheme: event.target.value || undefined,
                      };
                      if (!event.target.value) {
                        delete scale.scheme;
                      }
                      setChannel(channel, { scale }, scope);
                    }}
                  >
                    <option value="">auto</option>
                    {schemes.map((scheme) => (
                      <option key={scheme} value={scheme}>
                        {scheme}
                      </option>
                    ))}
                  </select>
                </label>
              );
            }
            return null;
          })}
        </div>
      )}
    </details>
  );
}
