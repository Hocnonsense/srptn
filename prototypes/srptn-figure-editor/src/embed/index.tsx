import { createRoot, type Root } from "react-dom/client";
import type { StoreApi } from "zustand/vanilla";

import type {
  FrontendRenderer,
  FrontendRendererArgs,
  FrontendState,
} from "@streamlit/component-v2-lib";

import { App } from "../components/App";
import { buildSpec } from "../lib/chart/engine/buildSpec";
import { validateSpec } from "../lib/chart/engine/validate";
import { validateChartState } from "../lib/chart/engine/validateState";
import {
  tableFromColumns,
  type VegaType,
} from "../lib/chart/schema/table-schema";
import { autoState } from "../lib/chart/state/auto-state";
import {
  createChartStore,
  type ChartStore,
} from "../lib/chart/state/chart-store";
import type { ChartState } from "../lib/chart/state/types";

interface EditorData {
  rows?: Record<string, unknown>[];
  columns?: { name: string; type: VegaType }[];
  initial?: ChartState | null;
  load_token?: string;
}

interface EditorValue {
  state: ChartState;
  spec: Record<string, unknown>;
  issues: unknown[];
}

interface EditorState extends FrontendState {
  value: EditorValue | null;
}

type Args = FrontendRendererArgs<EditorState, EditorData>;

/**
 * Runtime state for one Streamlit figure-editor instance, kept across
 * Streamlit reruns (each rerun triggers one `render()` call).
 */
class EditorMount {
  /**
   * Local browser object (not serializable), unmounted in cleanup.
   * Holds the Fiber tree, so hooks state survives subsequent render() calls.
   */
  private readonly root: Root;

  /**
   * Per-instance chart state; independent for every mounted editor.
   */
  private readonly store: StoreApi<ChartStore>;

  /**
   * unsubscribe function of the zustand store,
   * called on cleanup to stop triggering `scheduleSend`.
   */
  private readonly unsubscribe: () => void;

  constructor(parentElement: HTMLElement | ShadowRoot) {
    const container = document.createElement("div");
    container.className = "figure-editor-root";
    parentElement.appendChild(container);

    this.root = createRoot(container);
    this.store = createChartStore();
    this.unsubscribe = this.store.subscribe(() => this.scheduleSend());
  }

  /**
   * `null` => never initialized for this instance
   * otherwise the last `data.load_token`.
   *
   * `null !== ""` is what makes the first render always initialize.
   */
  private token: string | null = null;

  /**
   * Dedup marker compared against the freshly serialized state inside `scheduleSend`:
   *  equal → early return, no timer set.
   *
   * `""` = never initialized for this instance, or reset after a token change.
   * Otherwise the last `JSON.stringify(state)` that passed dedup
   * (pending in the debounce timer or already sent).
   */
  private lastSent = "";

  /**
   * 200ms debounce timer handle for `scheduleSend`; `undefined` when no task is pending.
   */
  private timer: ReturnType<typeof setTimeout> | undefined;

  /**
   * Latest `Args` (notably `setStateValue`) from the most recent `render()`,
   * overwritten on every call.
   * Needed because `send` runs asynchronously from the debounce timer,
   * after `render()` has already returned.
   */
  private args: Args | undefined;

  render(args: Args): void {
    this.args = args;

    const token = args.data?.load_token ?? "";
    if (this.token !== token) {
      const table = tableFromColumns(
        args.data?.columns ?? [],
        args.data?.rows ?? [],
      );
      this.store.getState().setTable(table);
      this.store.setState({
        state: args.data?.initial ?? autoState(table),
      });
      this.token = token;
      this.lastSent = "";
      this.scheduleSend();
    }

    this.root.render(<App store={this.store} />);
  }

  dispose(): void {
    if (this.timer) {
      clearTimeout(this.timer);
    }
    this.unsubscribe();
    this.root.unmount();
  }

  private send(): void {
    if (!this.args) {
      return;
    }
    const { state, table } = this.store.getState();
    const preview = buildSpec(state, { includeData: true, rows: table.rows });

    this.args.setStateValue("value", {
      state,
      spec: buildSpec(state, { includeData: false }),
      issues: [...validateChartState(state), ...validateSpec(preview)],
    });
  }

  private scheduleSend(): void {
    const serialized = JSON.stringify(this.store.getState().state);
    if (serialized === this.lastSent) {
      return;
    }
    this.lastSent = serialized;
    if (this.timer) {
      clearTimeout(this.timer);
    }
    this.timer = setTimeout(() => this.send(), 200);
  }
}

/**
 * Streamlit runtime in browser keeps parentElement identity across reruns,
 * so use it as WeakMap key to bind per-instance EditorMount state.
 *
 * parentElement = DOM container Streamlit provides per component instance
 * (ShadowRoot when isolate_styles=True); EditorMount renders into a child div of it.
 */
const mounts = new WeakMap<HTMLElement | ShadowRoot, EditorMount>();

const FigureEditor: FrontendRenderer<EditorState, EditorData> = (args) => {
  const { parentElement } = args;
  let mount = mounts.get(parentElement);
  if (!mount) {
    mount = new EditorMount(parentElement);
    mounts.set(parentElement, mount);
  }

  mount.render(args);

  return () => {
    mount.dispose();
    mounts.delete(parentElement);
  };
};

export default FigureEditor;
