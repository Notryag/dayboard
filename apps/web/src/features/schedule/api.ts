import { apiClient, requireApiData } from "@/lib/api/typedClient";
import type {
  CalendarEntryUpdate,
  ScheduleMutation,
  TaskItemUpdate,
} from "@/lib/api/types";
import type { CalendarEntry, TaskItem } from "./types";

export async function getCalendarEntryPage(
  date: string,
  cursor?: string,
  signal?: AbortSignal,
) {
  const { data } = await apiClient.GET("/api/calendar-entries", {
    params: { query: { date, cursor, limit: 20 } },
    signal,
  });
  return requireApiData(data);
}

export async function getUndatedTaskPage(cursor?: string, signal?: AbortSignal) {
  const { data } = await apiClient.GET("/api/task-items", {
    params: { query: { status: "all", due_kind: "undated", cursor, limit: 20 } },
    signal,
  });
  return requireApiData(data);
}

export async function getDatedTaskPage(
  date: string,
  cursor?: string,
  signal?: AbortSignal,
) {
  const { data } = await apiClient.GET("/api/task-items", {
    params: { query: { status: "all", due_kind: "dated", date, cursor, limit: 20 } },
    signal,
  });
  return requireApiData(data);
}

export async function cancelCalendarEntry(entry: CalendarEntry): Promise<CalendarEntry> {
  const { data } = await apiClient.POST("/api/calendar-entries/{entry_id}/cancel", {
    params: { path: { entry_id: entry.id } },
    body: { expected_row_version: entry.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function completeCalendarEntry(entry: CalendarEntry): Promise<CalendarEntry> {
  const { data } = await apiClient.POST("/api/calendar-entries/{entry_id}/complete", {
    params: { path: { entry_id: entry.id } },
    body: { expected_row_version: entry.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function reopenCalendarEntry(entry: CalendarEntry): Promise<CalendarEntry> {
  const { data } = await apiClient.POST("/api/calendar-entries/{entry_id}/reopen", {
    params: { path: { entry_id: entry.id } },
    body: { expected_row_version: entry.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function completeTaskItem(task: TaskItem): Promise<TaskItem> {
  const { data } = await apiClient.POST("/api/task-items/{task_id}/complete", {
    params: { path: { task_id: task.id } },
    body: { expected_row_version: task.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function reopenTaskItem(task: TaskItem): Promise<TaskItem> {
  const { data } = await apiClient.POST("/api/task-items/{task_id}/reopen", {
    params: { path: { task_id: task.id } },
    body: { expected_row_version: task.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function cancelTaskItem(task: TaskItem): Promise<TaskItem> {
  const { data } = await apiClient.POST("/api/task-items/{task_id}/cancel", {
    params: { path: { task_id: task.id } },
    body: { expected_row_version: task.row_version } satisfies ScheduleMutation,
  });
  return requireApiData(data);
}

export async function updateCalendarEntry(
  entry: CalendarEntry,
  input:
    | { title: string; timingKind: "anytime"; scheduledDate: string }
    | { title: string; timingKind: "timed"; startTime: string; durationMinutes: number },
): Promise<CalendarEntry> {
  const { data } = await apiClient.PUT("/api/calendar-entries/{entry_id}", {
    params: { path: { entry_id: entry.id } },
    body: {
      expected_row_version: entry.row_version,
      title: input.title,
      timing_kind: input.timingKind,
      scheduled_date: input.timingKind === "anytime" ? input.scheduledDate : null,
      start_time: input.timingKind === "timed" ? input.startTime : null,
      duration_minutes: input.timingKind === "timed" ? input.durationMinutes : null,
    } satisfies CalendarEntryUpdate,
  });
  return requireApiData(data);
}

export async function updateTaskItem(
  task: TaskItem,
  input: { title: string; dueAt: string | null },
): Promise<TaskItem> {
  const { data } = await apiClient.PUT("/api/task-items/{task_id}", {
    params: { path: { task_id: task.id } },
    body: {
      expected_row_version: task.row_version,
      title: input.title,
      due_at: input.dueAt,
    } satisfies TaskItemUpdate,
  });
  return requireApiData(data);
}
