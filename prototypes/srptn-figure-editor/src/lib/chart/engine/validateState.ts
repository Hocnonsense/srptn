import type { ChartState, ChannelState } from "../state/types";
import {
  activeDeriveKind,
  channelFnAllowed,
  hasDerive,
} from "./channelFn";
import { DERIVE_SPECS } from "./transforms";
import type { ValidationIssue } from "./validate";

const RAW_MEASURES = new Set(["x", "y"]);

export function validateChartState(state: ChartState): ValidationIssue[] {
  const issues: ValidationIssue[] = [
    ...validateFacets(state),
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
      !hasDerive(channelState)
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
    const derive = activeDeriveKind(channelState);
    const fields = [
      channelState.aggregate ? "aggregate" : undefined,
      derive,
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
    if (derive && !channelFnAllowed(derive, channelState.type)) {
      const types = DERIVE_SPECS[derive].sourceTypes ?? [];
      const label = derive.charAt(0).toUpperCase() + derive.slice(1);
      issues.push({
        severity: "error",
        path,
        message: `${label} requires ${types.join(" or ")} field.`,
      });
    }
  }
  return issues;
}

function validateFacets(state: ChartState): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const shared = state.shared.encoding;
  const facetKeys = ["row", "column", "facet"].filter(
    (channel) => shared[channel],
  );
  if (facetKeys.length > 1 && facetKeys.includes("facet")) {
    issues.push({
      severity: "error",
      path: "/shared/encoding/facet",
      message:
        "Use either facet or row/column, not both.",
    });
  }
  state.layers.forEach((layer, index) => {
    for (const channel of ["row", "column", "facet"]) {
      if (layer.encoding[channel]) {
        issues.push({
          severity: "error",
          path: `/layers/${index}/encoding/${channel}`,
          message: "Facet channels belong to shared encoding.",
        });
      }
    }
  });
  return issues;
}
