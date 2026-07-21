"use client";

import { useInfiniteQuery, type QueryKey } from "@tanstack/react-query";
import { userFacingApiError } from "@/lib/api/client";
import type { SchedulePage } from "./types";

type PageLoader<T> = (cursor?: string, signal?: AbortSignal) => Promise<SchedulePage<T>>;

type UseSchedulePageOptions<T> = {
  loadErrorMessage: string;
  loadMoreErrorMessage: string;
  loadPage: PageLoader<T>;
  queryKey: QueryKey;
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
  queryKey,
}: UseSchedulePageOptions<T>): SchedulePageResource<T> {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => loadPage(pageParam ?? undefined, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);
  const cursor = pages.at(-1)?.next_cursor ?? null;
  const fallback = query.isFetchNextPageError ? loadMoreErrorMessage : loadErrorMessage;
  const error = query.error ? userFacingApiError(query.error, fallback) : null;

  return {
    cursor,
    error,
    items,
    loadMore: () => { if (query.hasNextPage) void query.fetchNextPage(); },
    loading: query.isPending || query.isFetchingNextPage,
    retry: () => { void query.refetch(); },
  };
}
