"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { userFacingApiError } from "@/lib/api/client";
import type { SchedulePage } from "./types";

type PageLoader<T> = (cursor?: string, signal?: AbortSignal) => Promise<SchedulePage<T>>;

type UseSchedulePageOptions<T> = {
  loadErrorMessage: string;
  loadMoreErrorMessage: string;
  loadPage: PageLoader<T>;
  reloadKey?: string | number;
};

export type SchedulePageResource<T> = {
  cursor: string | null;
  error: string | null;
  items: T[];
  loadMore: () => void;
  loading: boolean;
  retry: () => void;
};

export function useSchedulePage<T>({
  loadErrorMessage,
  loadMoreErrorMessage,
  loadPage,
  reloadKey = 0,
}: UseSchedulePageOptions<T>): SchedulePageResource<T> {
  const requestRef = useRef<AbortController | null>(null);
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (nextCursor?: string) => {
      const append = Boolean(nextCursor);
      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const page = await loadPage(nextCursor, controller.signal);
        setItems((current) => (append ? [...current, ...page.items] : page.items));
        setCursor(page.next_cursor ?? null);
      } catch (caught: unknown) {
        if (!controller.signal.aborted) {
          setError(userFacingApiError(caught, append ? loadMoreErrorMessage : loadErrorMessage));
        }
      } finally {
        if (requestRef.current === controller) {
          requestRef.current = null;
          setLoading(false);
        }
      }
    },
    [loadErrorMessage, loadMoreErrorMessage, loadPage],
  );

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void load();
    });
    return () => {
      active = false;
      const controller = requestRef.current;
      controller?.abort();
      if (requestRef.current === controller) requestRef.current = null;
    };
  }, [load, reloadKey]);

  const retry = useCallback(() => void load(), [load]);
  const loadMore = useCallback(() => {
    if (cursor && !loading) void load(cursor);
  }, [cursor, load, loading]);

  return { cursor, error, items, loadMore, loading, retry };
}
