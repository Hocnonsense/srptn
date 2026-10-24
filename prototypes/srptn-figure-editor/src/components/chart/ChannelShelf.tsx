import { useState } from "react";

import {
  AGGREGATE_OPS,
  CHANNELS,
  FACET_CHANNELS,
  markChannelRule,
} from "../../lib/chart/metamodel/rules";
import { isVegaType, VEGA_TYPE_META } from "../../lib/chart/schema/table-schema";
import {
  clampLayerIndex,
  type ChartState,
  type Scope,
} from "../../lib/chart/state/types";
import { useChartStore } from "../../lib/chart/state/chart-store";
import {
  aggregateOutputType,
  collectAggregateOps,
} from "../../lib/chart/engine/aggregate";
import {
  ENCODING_DERIVE_KINDS,
  channelFnAllowed,
  channelFnKind,
  channelFnLabel,
  channelFnParams,
  channelFnPatch,
} from "../../lib/chart/engine/channelFn";
import { derivedFields } from "../../lib/chart/engine/fields";
import type { ChoiceOption } from "../../lib/chart/engine/options";
import "./ChannelShelf.css";
import { ParamControl } from "./ParamControl";
import { Row, RowList } from "./Rows";
import { TypeBadge } from "./TypeBadge";

export function ChannelShelf({
  scope = "layer",
  state: override,
}: {
  scope?: Scope;
  state?: ChartState;
}) {
  const storeState = useChartStore((store) => store.state);
  const state = override ?? storeState;
  const table = useChartStore((store) => store.table);
  const storeActiveLayerIndex = useChartStore(
    (store) => store.activeLayerIndex,
  );
  const activeLayerIndex = clampLayerIndex(state, storeActiveLayerIndex);
  const options = useChartStore((store) => store.options);
  const setField = useChartStore((store) => store.setField);
  const setChannel = useChartStore((store) => store.setChannel);
  const removeChannel = useChartStore((store) => store.removeChannel);
  const [editing, setEditing] = useState<string | null>(null);

  const layer = state.layers[activeLayerIndex] ?? state.layers[0];
  const baseNames = table.columns.map((column) => column.name);
  const sharedAggregates = collectAggregateOps(state.shared.transform);
  const layerAggregates =
    scope === "shared" ? [] : collectAggregateOps(layer.transform);
  const sharedNames = [
    ...baseNames,
    ...sharedAggregates.map((aggregate) => aggregate.name),
  ];
  const sharedFields = derivedFields(sharedNames, state.shared.transform);
  const layerFields =
    scope === "shared"
      ? []
      : derivedFields(
        [
          ...sharedNames,
          ...sharedFields.map((field) => field.name),
          ...layerAggregates.map((aggregate) => aggregate.name),
        ],
        layer.transform,
      );
  const calculatedFields = [...sharedFields, ...layerFields];
  const aggregateFields = [...sharedAggregates, ...layerAggregates];
  const aggregateOptions: ChoiceOption[] = aggregateFields.map((output) => ({
    value: output.name,
    label: output.name,
    description: `${output.op}(${output.field ?? ""})`,
  }));
  const source = scope === "shared" ? state.shared.encoding : layer.encoding;
  const active = Object.keys(source);
  const channelsInLayers = new Set(
    state.layers.flatMap((item) => Object.keys(item.encoding)),
  );
  const sharedChannels = [
    ...CHANNELS,
    ...[...FACET_CHANNELS].filter((channel) => channel !== "facet"),
  ];
  const addable = (
    scope === "shared" ? sharedChannels : CHANNELS
  ).filter((channel) => {
    if (active.includes(channel)) {
      return false;
    }
    if (scope === "shared") {
      if (FACET_CHANNELS.has(channel as never)) {
        return true;
      }
      return (
        channelsInLayers.has(channel) &&
        state.layers.some(
          (item) =>
            markChannelRule(item.mark, channel).status !== "invalid",
        )
      );
    }
    return markChannelRule(layer.mark, channel).status !== "invalid";
  });

  const moveChannel = (from: string, to: string) => {
    if (!to) {
      removeChannel(from, scope);
      return;
    }
    if (to === from) {
      return;
    }
    setChannel(to, source[from] ?? {}, scope);
    removeChannel(from, scope);
  };

  const addChannel = () => {
    const channel = addable[0];
    if (channel) {
      setChannel(channel, {}, scope);
      setEditing(channel);
    }
  };

  return (
    <section className="panel">
      <div className="chip-row">
        {active.map((channel) => (
          <button
            type="button"
            key={channel}
            className={`chip ${editing === channel ? "active" : ""
              }`}
            onClick={() =>
              setEditing(editing === channel ? null : channel)
            }
          >
            {channel}={channelFnLabel(source[channel] ?? {})}
          </button>
        ))}
        <button
          type="button"
          className="icon-button"
          title="Add channel"
          onClick={addChannel}
          disabled={addable.length === 0}
        > + </button>
        <div className="panel-heading channel-scope">
          <h3>{scope === "shared" ? "Shared channels" : "Layer channels"}</h3>
        </div>
      </div>

      {editing && active.includes(editing) ? (
        <RowList className="channel-list">
          {active.filter((channel) => channel === editing).map((channel) => {
            const channelState = source[channel] ?? {};
            const fieldOptions = options(channel, scope);
            const derivedOptions: ChoiceOption[] = calculatedFields
              .filter(
                (field) =>
                  !fieldOptions.some(
                    (option) => String(option.value) === field.name,
                  ),
              )
              .map((field) => ({
                value: field.name,
                label: `${field.name}`,
                description: "Derived field",
              }));
            const allFieldOptions = [
              ...fieldOptions,
              ...aggregateOptions,
              ...derivedOptions,
            ];
            const fieldValue = String(channelState.field ?? "");
            const fieldType = String(channelState.type ?? "");
            const typedFieldType = isVegaType(fieldType)
              ? fieldType
              : undefined;
            const canAggregate = fieldType === "quantitative";
            const fn = channelFnKind(channelState);
            const params = channelFnParams(fn);
            const setFunction = (value: string) => {
              if (value === "none") {
                setChannel(channel, channelFnPatch("none"), scope);
              } else if (
                (ENCODING_DERIVE_KINDS as readonly string[]).includes(value)
              ) {
                setChannel(channel, channelFnPatch(value), scope);
              } else {
                setChannel(
                  channel,
                  channelFnPatch("aggregate", value),
                  scope,
                );
              }
            };

            return (
              <Row className="channel-row" key={channel}>
                <div className="channel-key">
                  <select
                    className="channel-select"
                    value={channel}
                    title="Channel"
                    onChange={(event) => {
                      const next = event.target.value;
                      setEditing(next || null);
                      moveChannel(channel, next);
                    }}
                  >
                    <option value="">—</option>
                    {[channel, ...addable].map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>

                  <div className="type-select-wrap" title="Field type">
                    <span className="type-select-value">
                      {typedFieldType ? <TypeBadge type={typedFieldType} /> : "?"}
                    </span>
                    <select
                      className="type-select"
                      value={typedFieldType ?? ""}
                      onChange={(event) =>
                        setChannel(
                          channel,
                          { type: event.target.value || undefined },
                          scope,
                        )
                      }
                    >
                      <option value="">?</option>
                      {Object.entries(VEGA_TYPE_META).map(([value, { label }]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <span className="channel-equals">=</span>

                <select
                  className="field-select"
                  value={fieldValue}
                  onChange={(event) => {
                    const value = event.target.value;
                    const aggregate = aggregateFields.find(
                      (field) => field.name === value,
                    );
                    if (aggregate) {
                      const sourceType = table.columns.find(
                        (column) => column.name === aggregate.field,
                      )?.type;
                      setChannel(
                        channel,
                        {
                          field: value,
                          type: aggregateOutputType(
                            aggregate.op,
                            sourceType,
                          ),
                        },
                        scope,
                      );
                      return;
                    }
                    const derived = calculatedFields.find(
                      (field) => field.name === value,
                    );
                    if (derived) {
                      setChannel(
                        channel,
                        {
                          field: value,
                          type: derived.type ?? channelState.type ?? "nominal",
                        },
                        scope,
                      );
                      return;
                    }
                    setField(channel, value || undefined, scope);
                  }}
                >
                  <option value="">—</option>
                  {allFieldOptions.map((option) => (
                    <option
                      key={String(option.value)}
                      value={String(option.value)}
                      disabled={option.disabled}
                      title={option.reason}
                    >
                      {option.label}
                    </option>
                  ))}
                </select>

                <select
                  className="field-select fn-select"
                  value={fn}
                  title="Field function"
                  onChange={(event) => setFunction(event.target.value)}
                >
                  <option value="none">fn: none</option>
                  <optgroup label="Aggregate">
                    <option value="count">count</option>
                    {canAggregate &&
                      AGGREGATE_OPS.filter((op) => op !== "count").map(
                        (op) => (
                          <option key={op} value={op}>
                            {op}
                          </option>
                        ),
                      )}
                  </optgroup>
                  {ENCODING_DERIVE_KINDS.filter((kind) =>
                    channelFnAllowed(kind, typedFieldType),
                  ).map((kind) => (
                    <option key={kind} value={kind}>
                      {kind}
                    </option>
                  ))}
                </select>

                {params.length > 0 && (
                  <div className="channel-params">
                    {params.map((param) => (
                      <ParamControl
                        key={param.key}
                        control={param}
                        className="channel-param"
                        value={param.value(channelState)}
                        onChange={(next) =>
                          setChannel(channel, param.patch(next), scope)
                        }
                      />
                    ))}
                  </div>
                )}

              </Row>
            );
          })}
        </RowList>
      ) : null}
    </section>
  );
}
