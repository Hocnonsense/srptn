import type { ChartState, ChannelState } from "../state/types";
import type { ValidationIssue } from "./validate";

const RAW_MEASURES = new Set(["x", "y"]);

export function validateChartState(state: ChartState): ValidationIssue[] {
  const issues: ValidationIssue[] = [
    ...validateEncoding(state.shared.encoding, "/shared/encoding"),
    ...groupKeyWarnings(
      state.shared.encoding,
      (channel) => `/shared/encoding/${channel}`,
    ),
  ];

  state.layers.forEach((layer, layerIndex) => {
    issues.push(
      ...validateEncoding(
        layer.encoding,
        `/layers/${layerIndex}/encoding`,
      ),
    );

    const effective = { ...state.shared.encoding, ...layer.encoding };
    issues.push(
      ...groupKeyWarnings(effective, (channel) =>
        channel in layer.encoding
          ? `/layers/${layerIndex}/encoding/${channel}`
          : `/shared/encoding/${channel}`,
      ),
    );
  });

  return dedupe(issues);
}

function groupKeyWarnings(
  encoding: Record<string, ChannelState>,
  pathFor: (channel: string) => string,
): ValidationIssue[] {
  if (!Object.values(encoding).some((channel) => channel.aggregate)) {
    return [];
  }
  const issues: ValidationIssue[] = [];
  for (const channel of RAW_MEASURES) {
    const channelState = encoding[channel];
    if (
      channelState?.field &&
      channelState.type === "quantitative" &&
      !channelState.aggregate &&
      !channelState.bin &&
      !channelState.timeUnit
    ) {
      issues.push({
        severity: "warning",
        path: pathFor(channel),
        message:
          "This raw quantitative channel becomes a group key because another channel aggregates.",
      });
    }
  }
  return issues;
}

function dedupe(issues: ValidationIssue[]): ValidationIssue[] {
  const seen = new Set<string>();
  return issues.filter((issue) => {
    const key = `${issue.severity}:${issue.path}:${issue.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function validateEncoding(
  encoding: Record<string, ChannelState>,
  pathPrefix: string,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  for (const [channel, channelState] of Object.entries(encoding)) {
    const path = `${pathPrefix}/${channel}`;
    const fields = [
      channelState.aggregate ? "aggregate" : undefined,
      channelState.bin ? "bin" : undefined,
      channelState.timeUnit ? "timeUnit" : undefined,
    ].filter(Boolean);

    if (fields.length > 1) {
      issues.push({
        severity: "error",
        path,
        message:
          "Choose one field function: aggregate, bin, or timeUnit are a pipeline, not parallel options.",
      });
    }

    if (
      channelState.aggregate &&
      channelState.aggregate !== "count" &&
      channelState.type !== "quantitative"
    ) {
      issues.push({
        severity: "error",
        path,
        message: "Aggregate requires a quantitative field.",
      });
    }
    if (
      channelState.bin &&
      channelState.type !== "quantitative" &&
      channelState.type !== "temporal"
    ) {
      issues.push({
        severity: "error",
        path,
        message: "Bin requires a quantitative or temporal field.",
      });
    }
    if (channelState.timeUnit && channelState.type !== "temporal") {
      issues.push({
        severity: "error",
        path,
        message: "timeUnit requires a temporal field.",
      });
    }
  }
  return issues;
}
