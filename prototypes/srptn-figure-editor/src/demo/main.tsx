import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "../components/App";
import { inferTableSchema } from "../lib/chart/schema/table-schema";
import { createChartStore } from "../lib/chart/state/chart-store";

const CSV_TEXT = `species,condition,time,expression,site,replicate,batch,dose,experiment_id,plate_id,well,instrument,operator,temperature_c,humidity_pct,cell_count,viability_pct,rna_integrity,measured_at,qc_flag,note
A,control,0,1.8,S1,1,B1,0,EXP-001,P001,A1,SeqStudio-01,li.wei,22.1,45.2,12000,98.1,9.2,2024-03-01T09:00:00,PASS,
A,control,1,2.1,S1,1,B1,0,EXP-001,P001,A2,SeqStudio-01,li.wei,22.3,45.0,12100,97.9,9.1,2024-03-01T09:30:00,PASS,
A,control,1,2.3,S1,2,B1,0,EXP-001,P001,A3,SeqStudio-01,li.wei,22.0,44.8,11950,98.0,9.3,2024-03-01T09:32:00,PASS,
A,control,2,2.8,S1,1,B1,0,EXP-001,P001,A4,SeqStudio-01,li.wei,22.2,45.1,12050,98.2,9.0,2024-03-01T10:00:00,PASS,
A,control,2,3.0,S1,2,B1,0,EXP-001,P001,A5,SeqStudio-01,li.wei,22.4,45.3,12020,97.8,9.2,2024-03-01T10:02:00,PASS,
A,treated,0,2.0,S1,1,B1,5,EXP-001,P001,B1,SeqStudio-01,li.wei,22.1,45.2,11800,96.5,8.9,2024-03-01T11:00:00,PASS,
A,treated,1,3.4,S1,1,B1,5,EXP-001,P001,B2,SeqStudio-01,li.wei,22.3,45.0,11750,96.1,8.8,2024-03-01T11:30:00,PASS,
A,treated,1,3.1,S1,2,B1,5,EXP-001,P001,B3,SeqStudio-01,li.wei,22.0,44.9,11720,96.3,8.7,2024-03-01T11:32:00,PASS,
A,treated,2,4.6,S1,1,B1,5,EXP-001,P001,B4,SeqStudio-01,li.wei,22.2,45.1,11600,95.8,8.5,2024-03-01T12:00:00,PASS,
A,treated,2,4.9,S1,2,B1,5,EXP-001,P001,B5,SeqStudio-01,li.wei,22.5,45.4,11580,95.5,8.6,2024-03-01T12:02:00,PASS,
B,control,0,1.5,S1,1,B1,0,EXP-002,P002,C1,SeqStudio-02,wang.fang,23.0,50.1,10500,97.2,8.8,2024-03-02T09:00:00,PASS,
B,control,0.5,1.6,S1,1,B1,0,EXP-002,P002,C2,SeqStudio-02,wang.fang,23.1,50.0,10480,97.0,8.7,2024-03-02T09:30:00,PASS,
B,control,1,1.7,S1,1,B1,0,EXP-002,P002,C3,SeqStudio-02,wang.fang,23.2,50.2,10450,97.1,8.9,2024-03-02T10:00:00,PASS,
B,control,1,1.5,S1,2,B1,0,EXP-002,P002,C4,SeqStudio-02,wang.fang,22.9,49.9,10460,96.9,8.6,2024-03-02T10:02:00,PASS,
B,control,2,2.2,S1,1,B1,0,EXP-002,P002,C5,SeqStudio-02,wang.fang,23.0,50.1,10300,96.8,8.5,2024-03-02T11:00:00,PASS,
B,control,2,2.4,S1,2,B2,0,EXP-002,P002,C6,SeqStudio-02,wang.fang,23.3,50.3,10280,96.6,8.4,2024-03-02T11:02:00,PASS,
B,treated,0,1.9,S1,1,B1,5,EXP-002,P002,D1,SeqStudio-02,wang.fang,23.0,50.1,10100,95.5,8.2,2024-03-02T12:00:00,PASS,
B,treated,0.5,2.4,S1,1,B1,5,EXP-002,P002,D2,SeqStudio-02,wang.fang,23.1,50.0,10080,95.3,8.1,2024-03-02T12:30:00,PASS,
B,treated,1,2.9,S1,1,B1,5,EXP-002,P002,D3,SeqStudio-02,wang.fang,23.2,50.2,10050,95.0,8.0,2024-03-02T13:00:00,PASS,
B,treated,1,3.1,S1,2,B1,5,EXP-002,P002,D4,SeqStudio-02,wang.fang,23.3,50.4,10020,94.8,7.9,2024-03-02T13:02:00,PASS,
B,treated,2,3.8,S1,1,B1,5,EXP-002,P002,D5,SeqStudio-02,wang.fang,23.4,50.5,9900,94.2,7.7,2024-03-02T14:00:00,PASS,
B,treated,2,3.6,S1,2,B2,5,EXP-002,P002,D6,SeqStudio-02,wang.fang,23.5,50.6,9880,94.0,7.6,2024-03-02T14:02:00,PASS,"batch effect, re-measured"
B,treated,4,4.4,S1,1,B2,5,EXP-002,P003,E1,SeqStudio-02,wang.fang,23.6,50.8,9500,92.5,7.2,2024-03-02T16:00:00,PASS,
B,treated,8,5.1,S1,1,B3,5,EXP-002,P003,E2,SeqStudio-02,wang.fang,23.7,51.0,9200,90.1,6.8,2024-03-02T20:00:00,WARN,"prolonged incubation, re-read"
C,control,0,2.2,S2,1,B1,0,EXP-003,P004,F1,NovaSeq-01,zhao.min,21.5,42.3,15000,98.5,9.5,2024-03-03T09:00:00,PASS,
C,control,1,2.4,S2,1,B1,0,EXP-003,P004,F2,NovaSeq-01,zhao.min,21.6,42.1,14980,98.4,9.4,2024-03-03T09:30:00,PASS,
C,control,1,2.6,S2,2,B1,0,EXP-003,P004,F3,NovaSeq-01,zhao.min,21.4,42.0,14950,98.3,9.3,2024-03-03T09:32:00,PASS,
C,control,2,3.1,S2,1,B1,0,EXP-003,P004,F4,NovaSeq-01,zhao.min,21.7,42.5,14800,98.2,9.2,2024-03-03T10:00:00,PASS,
C,control,2,2.9,S2,2,B2,0,EXP-003,P004,F5,NovaSeq-01,zhao.min,21.8,42.6,14780,98.0,9.1,2024-03-03T10:02:00,PASS,
C,treated,0,2.8,S2,1,B1,5,EXP-003,P004,G1,NovaSeq-01,zhao.min,21.5,42.3,14500,97.5,8.9,2024-03-03T11:00:00,PASS,
C,treated,1,3.8,S2,1,B1,5,EXP-003,P004,G2,NovaSeq-01,zhao.min,21.6,42.2,14450,97.2,8.8,2024-03-03T11:30:00,PASS,
C,treated,1,4.0,S2,2,B1,5,EXP-003,P004,G3,NovaSeq-01,zhao.min,21.7,42.4,14420,97.0,8.7,2024-03-03T11:32:00,PASS,
C,treated,2,5.2,S2,1,B1,5,EXP-003,P004,G4,NovaSeq-01,zhao.min,21.8,42.5,14200,96.5,8.5,2024-03-03T12:00:00,PASS,"with ""internal std"" calibration"
C,treated,2,5.5,S2,2,B2,5,EXP-003,P004,G5,NovaSeq-01,zhao.min,21.9,42.7,14180,96.3,8.4,2024-03-03T12:02:00,PASS,
C,treated,4,6.8,S2,1,B2,5,EXP-003,P005,H1,NovaSeq-01,zhao.min,22.0,43.0,13800,95.8,8.0,2024-03-03T14:00:00,PASS,
C,treated,4,6.5,S2,2,B2,5,EXP-003,P005,H2,NovaSeq-01,zhao.min,22.1,43.1,13780,95.5,7.9,2024-03-03T14:02:00,WARN,
D,control,0,1.6,S2,1,B1,0,EXP-004,P006,J1,MiniSeq-01,sun.hao,20.8,40.5,11000,97.5,9.0,2024-03-04T09:00:00,PASS,
D,control,1,1.9,S2,1,B1,0,EXP-004,P006,J2,MiniSeq-01,sun.hao,20.9,40.3,10980,97.3,8.9,2024-03-04T09:30:00,PASS,
D,control,1,2.0,S2,2,B1,0,EXP-004,P006,J3,MiniSeq-01,sun.hao,20.7,40.2,10950,97.1,8.8,2024-03-04T09:32:00,PASS,
D,control,2,2.6,S2,1,B1,0,EXP-004,P006,J4,MiniSeq-01,sun.hao,21.0,40.6,10800,96.9,8.7,2024-03-04T10:00:00,PASS,
D,control,2,,S2,2,B2,0,EXP-004,P006,J5,MiniSeq-01,sun.hao,21.1,40.8,,,8.6,2024-03-04T10:02:00,FAIL,sample lost
D,treated,0,2.1,S2,1,B1,5,EXP-004,P006,K1,MiniSeq-01,sun.hao,20.8,40.5,10600,96.0,8.4,2024-03-04T11:00:00,PASS,
D,treated,1,3.2,S2,1,B1,5,EXP-004,P006,K2,MiniSeq-01,sun.hao,20.9,40.4,10550,95.7,8.3,2024-03-04T11:30:00,PASS,
D,treated,1,3.0,S2,2,B1,5,EXP-004,P006,K3,MiniSeq-01,sun.hao,21.0,40.6,10520,95.5,8.2,2024-03-04T11:32:00,PASS,
D,treated,2,4.1,S2,1,B1,5,EXP-004,P006,K4,MiniSeq-01,sun.hao,21.1,40.7,10300,95.0,8.0,2024-03-04T12:00:00,PASS,
D,treated,2,4.3,S2,2,B2,5,EXP-004,P006,K5,MiniSeq-01,sun.hao,21.2,40.9,10280,94.8,7.9,2024-03-04T12:02:00,PASS,
D,treated,8,5.6,S2,1,B3,5,EXP-004,P007,L1,MiniSeq-01,sun.hao,21.3,41.0,9800,92.0,7.3,2024-03-04T18:00:00,WARN,very high expression
E,control,0,3.1,S3,1,B3,0,EXP-005,P008,M1,NextSeq-01,guo.lei,24.0,55.2,13000,98.8,9.6,2024-03-05T09:00:00,PASS,
E,control,1,3.3,S3,1,B3,0,EXP-005,P008,M2,NextSeq-01,guo.lei,24.1,55.0,12980,98.7,9.5,2024-03-05T09:30:00,PASS,
E,control,2,3.9,S3,1,B3,0,EXP-005,P008,M3,NextSeq-01,guo.lei,24.2,55.3,12950,98.6,9.4,2024-03-05T10:00:00,PASS,
E,treated,0,3.5,S3,1,B3,10,EXP-005,P008,N1,NextSeq-01,guo.lei,24.0,55.2,12700,97.9,9.0,2024-03-05T11:00:00,PASS,
E,treated,1,4.8,S3,1,B3,10,EXP-005,P008,N2,NextSeq-01,guo.lei,24.1,55.1,12650,97.6,8.9,2024-03-05T11:30:00,PASS,
E,treated,2,6.2,S3,1,B3,10,EXP-005,P008,N3,NextSeq-01,guo.lei,24.3,55.4,12400,97.0,8.7,2024-03-05T12:00:00,PASS,
E,treated,4,7.9,S3,1,B3,10,EXP-005,P008,N4,NextSeq-01,guo.lei,24.4,55.6,12000,96.2,8.3,2024-03-05T14:00:00,PASS,
E,treated,4,8.1,S3,2,B3,10,EXP-005,P008,N5,NextSeq-01,guo.lei,24.5,55.7,11980,96.0,8.2,2024-03-05T14:02:00,WARN,
E,treated,8,9.3,S3,1,B4,25,EXP-005,P009,P1,NextSeq-01,guo.lei,24.6,55.9,11500,94.5,7.8,2024-03-05T20:00:00,PENDING,"dose escalation, see protocol v3"
F,control,1,4.2,S3,1,B4,0,EXP-006,P010,Q1,NextSeq-01,he.yan,25.0,58.0,8000,96.0,8.1,2024-03-06T09:00:00,PENDING,single observation`;

function parseCSV(text: string) {
  const src = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (inQuotes) {
      if (ch === '"') {
        if (src[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(field); field = '';
    } else if (ch === '\n') {
      row.push(field); rows.push(row); row = []; field = '';
    } else field += ch;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.some(c => c.trim() !== ''));
}
const NUMERIC_FIELDS = new Set(['time', 'expression', 'replicate', 'dose']);

function toRows(csvText: string) {
  const [header, ...records] = parseCSV(csvText);
  const cols = header.map(h => h.trim());
  return records.map(rec => {
    const obj: Record<string, string | number | null> = {};
    cols.forEach((col: string, i: number) => {
      const raw = (rec[i] ?? '').trim();
      if (raw === '') { obj[col] = null; return; }
      obj[col] = NUMERIC_FIELDS.has(col) ? Number(raw) : raw;
    });
    return obj;
  });
}

const ROWS = toRows(CSV_TEXT);


const chartStore = createChartStore();
const store = chartStore.getState();
store.setTable(inferTableSchema(ROWS));
store.setField("x", "time");
store.setField("y", "expression");
store.setField("color", "condition");

createRoot(document.getElementById("root")!).render(<StrictMode><App store={chartStore} /></StrictMode>);
