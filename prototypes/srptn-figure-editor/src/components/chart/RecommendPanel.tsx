import { useCallback, useEffect, useMemo, useState } from "react";

import type { Recommendation } from "../../lib/chart/recommend/types";
import { thumbnailJobs } from "../../lib/chart/recommend/thumbnails";
import type { TableSchema } from "../../lib/chart/schema/table-schema";
import type { ChartState } from "../../lib/chart/state/types";
import "./RecommendPanel.css";
import { useGeneratedRecommendations } from "./useGeneratedRecommendations";
import { useThumbnailImages } from "./useThumbnailImages";

const PAGE_SIZE = 6;

export function RecommendPanel({
  table,
  baseline,
  open,
  specEditing,
  error,
  onOpen,
  onPreview,
  onApply,
  onCancel,
}: {
  table: TableSchema;
  baseline: ChartState | null;
  open: boolean;
  specEditing: boolean;
  error?: string;
  onOpen: () => void;
  onPreview: (state: ChartState | null) => void;
  onApply: (state: ChartState) => void;
  onCancel: () => void;
}) {
  const {
    recommendations,
    loading: generating,
    error: workerError,
  } = useGeneratedRecommendations({
    table,
    state: baseline,
    enabled: open,
  });
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    setSelected(null);
    setPage(0);
    onPreview(null);
  }, [baseline, onPreview]);

  const totalPages = Math.max(
    1,
    Math.ceil(recommendations.length / PAGE_SIZE),
  );
  const currentPage = Math.min(page, totalPages - 1);
  const pageItems = useMemo(
    () =>
      recommendations.slice(
        currentPage * PAGE_SIZE,
        (currentPage + 1) * PAGE_SIZE,
      ),
    [recommendations, currentPage],
  );
  const jobs = useMemo(
    () => (baseline ? thumbnailJobs(baseline, pageItems) : []),
    [baseline, pageItems],
  );
  const { images, loading: thumbLoading } = useThumbnailImages(jobs, table);

  useEffect(() => {
    if (page > totalPages - 1) {
      setPage(totalPages - 1);
    }
  }, [page, totalPages]);

  const choose = useCallback(
    (recommendation: Recommendation) => {
      if (selected?.id === recommendation.id) {
        setSelected(null);
        onPreview(null);
        return;
      }
      setSelected(recommendation);
      onPreview(recommendation.state);
    },
    [onPreview, selected],
  );

  const message = error ?? workerError;

  return (
    <section
      className={`panel panel-stack recommend-panel ${open ? "is-open" : ""}`}
    >
      <div className="recommend-heading">
        <button
          type="button"
          className="panel-toggle recommend-toggle"
          onClick={open ? onCancel : onOpen}
          disabled={!open && (specEditing || table.columns.length === 0)}
        >
          <span>Recommended</span>
          {!open && <span className="muted">show recommendations</span>}
        </button>
        {open && (
          <div className="recommend-actions">
            <button
              type="button"
              onClick={() => setPage(Math.max(0, currentPage - 1))}
              disabled={currentPage === 0}
            >
              ‹ Prev
            </button>
            <span className="muted">
              Page {currentPage + 1} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() =>
                setPage(Math.min(totalPages - 1, currentPage + 1))
              }
              disabled={currentPage >= totalPages - 1}
            >
              Next ›
            </button>
            <span className="muted">
              {generating
                ? "Updating…"
                : `${recommendations.length} recommendation${recommendations.length === 1 ? "" : "s"
                }`}
            </span>
            <span className="recommend-actions-spacer" />
            <button
              type="button"
              onClick={() => selected && onApply(selected.state)}
              disabled={!selected}
            >
              Apply
            </button>
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        )}
      </div>
      {!open ? (
        <div className="recommend-entry">
          <p className="muted">
            Generate next-step recommendations from the current chart. Opening
            the panel locks the editor above.
          </p>
        </div>
      ) : (
        <>
          {message && <div className="recommend-error">{message}</div>}
          {generating && recommendations.length === 0 && (
            <div className="recommend-loading">
              Computing recommendations…
            </div>
          )}
          {!generating && recommendations.length === 0 && baseline && (
            <div className="recommend-loading">
              No further recommendations found for this chart.
            </div>
          )}
          {pageItems.length > 0 && (
            <div className="recommend-grid">
              {pageItems.map((item, index) => {
                const key = jobs[index]?.key;
                const image = key ? images[key] : undefined;
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`recommend-card ${item.id === selected?.id ? "is-selected" : ""
                      }`}
                    aria-pressed={item.id === selected?.id}
                    onClick={() => choose(item)}
                  >
                    <div className="recommend-thumb">
                      {image ? (
                        <img src={image} alt="" />
                      ) : (
                        <div
                          className={`recommend-thumb-placeholder ${thumbLoading ? "is-loading" : ""
                            }`}
                        />
                      )}
                    </div>
                    <div className="recommend-card-body">
                      <strong>{item.title}</strong>
                      <span className="recommend-description">
                        {item.description}
                      </span>
                    </div>
                  </button>
                );
              })}
              {Array.from(
                { length: PAGE_SIZE - pageItems.length },
                (_, index) => (
                  <div
                    key={`placeholder-${index}`}
                    className="recommend-card is-placeholder"
                    aria-hidden="true"
                  >
                    <div className="recommend-thumb" />
                    <div className="recommend-card-body" />
                  </div>
                ),
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
