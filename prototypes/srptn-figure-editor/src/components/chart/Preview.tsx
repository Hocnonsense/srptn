import { useEffect, useRef } from "react";
import { version as vegaLiteVersion } from "vega-lite";
import embed from "vega-embed";

import type { ValidationIssue } from "../../lib/chart/engine/validate";
import "./Preview.css";

export function Preview({
  spec,
  issues,
}: {
  spec: Record<string, unknown>;
  issues: ValidationIssue[];
}) {
  const element = useRef<HTMLDivElement>(null);
  const error = issues.find((issue) => issue.severity === "error");

  useEffect(() => {
    if (!element.current || error) {
      return;
    }
    let finalized = false;
    embed(element.current, spec as never, {
      actions: false,
      renderer: "canvas",
    })
      .then((result) => {
        if (finalized) {
          result.finalize();
        }
      })
      .catch(() => {
        // Errors are surfaced by the validation panel.
      });
    return () => {
      finalized = true;
      element.current?.replaceChildren();
    };
  }, [spec, error]);

  return (
    <section className="panel preview-panel">
      <div className="panel-heading">
        <h2>Preview</h2>
        <span className="muted">Vega-Lite {vegaLiteVersion}</span>
      </div>
      {error ? (
        <div className="preview-error">
          <strong>Preview unavailable</strong>
          <span>{error.message}</span>
        </div>
      ) : (
        <div className="chart-host" ref={element} />
      )}
      {issues.length > 0 && (
        <div className="preview-issues">
          <div className="preview-issues-heading">Issues ({issues.length})</div>
          <ul>
            {issues.map((issue, index) => (
              <li key={`${issue.path}-${index}`} className={issue.severity}>
                <span>{issue.severity}</span>
                <code>{issue.path}</code>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
