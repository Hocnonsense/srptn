import type { TableSchema } from "../../lib/chart/schema/table-schema";
import { TypeBadge } from "./TypeBadge";
import "./DataPanel.css";

export function DataPanel({ table }: { table: TableSchema }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Data Summary</h2>
        <span className="muted">{table.columns.length} columns × {table.rows.length} rows</span>
      </div>
      <div className="data-table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Distinct</th>
              <th>Range / sample</th>
            </tr>
          </thead>
          <tbody>
            {table.columns.map((column) => (
              <tr key={column.name}>
                <td>{column.name}</td>
                <td><TypeBadge type={column.type} /> {column.type}</td>
                <td>{column.distinctCount ?? "—"}</td>
                <td className="sample">
                  {column.minimum !== undefined &&
                    column.maximum !== undefined
                    ? `${String(column.minimum)} … ${String(column.maximum)}`
                    : column.sampleValues.map(String).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
