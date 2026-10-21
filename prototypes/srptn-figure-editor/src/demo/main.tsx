import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "../components/App";
import { inferTableSchema } from "../lib/chart/schema/table-schema";
import { createChartStore } from "../lib/chart/state/chart-store";

const ROWS = [
  { species: "A", condition: "control", time: 1, expression: 2.1, site: "S1" },
  { species: "A", condition: "control", time: 2, expression: 2.8, site: "S1" },
  { species: "A", condition: "treated", time: 1, expression: 3.4, site: "S1" },
  { species: "A", condition: "treated", time: 2, expression: 4.6, site: "S1" },
  { species: "B", condition: "control", time: 1, expression: 1.7, site: "S1" },
  { species: "B", condition: "control", time: 2, expression: 2.2, site: "S1" },
  { species: "B", condition: "treated", time: 1, expression: 2.9, site: "S1" },
  { species: "B", condition: "treated", time: 2, expression: 3.8, site: "S1" },
  { species: "C", condition: "control", time: 1, expression: 2.4, site: "S2" },
  { species: "C", condition: "control", time: 2, expression: 3.1, site: "S2" },
  { species: "C", condition: "treated", time: 1, expression: 3.8, site: "S2" },
  { species: "C", condition: "treated", time: 2, expression: 5.2, site: "S2" },
  { species: "D", condition: "control", time: 1, expression: 1.9, site: "S2" },
  { species: "D", condition: "control", time: 2, expression: 2.6, site: "S2" },
  { species: "D", condition: "treated", time: 1, expression: 3.2, site: "S2" },
  { species: "D", condition: "treated", time: 2, expression: 4.1, site: "S2" },
];

const chartStore = createChartStore();
const store = chartStore.getState();
store.setTable(inferTableSchema(ROWS));
store.setField("x", "time");
store.setField("y", "expression");
store.setField("color", "condition");

createRoot(document.getElementById("root")!).render(<StrictMode><App store={chartStore} /></StrictMode>);
