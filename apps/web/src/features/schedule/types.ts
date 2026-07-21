import type {
  CalendarEntry,
  CalendarSchedulePage,
  TaskItem,
  TaskSchedulePage,
} from "@/lib/api/types";

export type { CalendarEntry, Reminder, TaskItem } from "@/lib/api/types";

type ApiSchedulePage = CalendarSchedulePage | TaskSchedulePage;

export type SchedulePage<T> = Omit<ApiSchedulePage, "items"> & { items: T[] };

export type ScheduleDisplayItem =
  | { kind: "calendar"; value: CalendarEntry }
  | { kind: "task"; value: TaskItem };

export type ScheduleResultPart = {
  tool_call_id: string;
  operation: string;
  item: ScheduleDisplayItem;
};

export type ScheduleChange = {
  undo?: {
    label: string;
    run: () => Promise<void>;
  };
};
