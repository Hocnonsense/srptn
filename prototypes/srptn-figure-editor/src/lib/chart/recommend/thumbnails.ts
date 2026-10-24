import embed from "vega-embed";

import { buildSpec } from "../engine/buildSpec";
import type { ChartState } from "../state/types";
import { applyChartPatch } from "./patch";
import type { PatchOp } from "./types";

export interface ThumbnailJob {
  key: string;
  state: ChartState;
}

interface ThumbnailSource {
  patch: PatchOp[];
}
export function thumbnailJobs(
  baseline: ChartState,
  recommendations: readonly ThumbnailSource[],
): ThumbnailJob[] {
  return recommendations.map((recommendation) => {
    const state = applyChartPatch(baseline, recommendation.patch);
    const spec = buildSpec(state);
    return {
      key: JSON.stringify(spec),
      state,
    };
  });
}

const THUMBNAIL_WIDTH = 280;
const THUMBNAIL_HEIGHT = 170;
export async function renderThumbnail(
  state: ChartState,
  rows: Record<string, unknown>[],
): Promise<string> {
  const spec = buildSpec(state, { includeData: true, rows });
  spec.width = THUMBNAIL_WIDTH;
  spec.height = THUMBNAIL_HEIGHT;

  if (typeof document === "undefined") {
    return "";
  }
  const host = document.createElement("div");
  host.style.position = "fixed";
  host.style.left = "-10000px";
  host.style.top = "0";
  host.style.width = `${THUMBNAIL_WIDTH}px`;
  host.style.height = `${THUMBNAIL_HEIGHT}px`;
  document.body.appendChild(host);
  try {
    const result = await embed(host, spec as never, {
      actions: false,
      renderer: "svg",
    });
    try {
      await result.view.runAsync();
      const svg = await result.view.toSVG();
      return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    } finally {
      result.finalize();
    }
  } catch {
    return "";
  } finally {
    host.remove();
  }
}
