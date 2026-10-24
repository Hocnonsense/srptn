import { useEffect, useRef, useState } from "react";

import type { TableSchema } from "../../lib/chart/schema/table-schema";
import {
  renderThumbnail,
  type ThumbnailJob,
} from "../../lib/chart/recommend/thumbnails";

export function useThumbnailImages(
  jobs: ThumbnailJob[],
  table: TableSchema,
): {
  images: Record<string, string>;
  loading: boolean;
} {
  const cacheRef = useRef(new Map<string, string>());
  const tableRef = useRef<TableSchema | null>(null);
  const [images, setImages] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (tableRef.current !== table) {
      tableRef.current = table;
      cacheRef.current.clear();
      setImages({});
    }
    const cache = cacheRef.current;
    let cancelled = false;
    const hits: Record<string, string> = {};
    const missing: ThumbnailJob[] = [];
    for (const job of jobs) {
      const hit = takeCached(cache, job.key);
      if (hit !== undefined) {
        hits[job.key] = hit;
      } else {
        missing.push(job);
      }
    }
    setImages(hits);
    if (missing.length === 0) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all(
      missing.map(async (job) => {
        const image = await renderThumbnail(job.state, table.rows);
        if (image) {
          storeCached(cache, job.key, image);
        }
        return [job.key, image] as const;
      }),
    )
      .then((entries) => {
        if (cancelled) {
          return;
        }
        setImages((current) => ({
          ...current,
          ...Object.fromEntries(entries),
        }));
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobs, table]);

  return { images, loading };
}

function takeCached(
  cache: Map<string, string>,
  key: string,
): string | undefined {
  const value = cache.get(key);
  if (value === undefined) {
    return undefined;
  }
  cache.delete(key);
  cache.set(key, value);
  return value;
}

function storeCached(
  cache: Map<string, string>,
  key: string,
  image: string,
): void {
  cache.delete(key);
  cache.set(key, image);
  while (cache.size > 48) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) {
      break;
    }
    cache.delete(oldest);
  }
}
