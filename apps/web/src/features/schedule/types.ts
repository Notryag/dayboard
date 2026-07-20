export type Reminder = {
  offset: string;
  anchor: "start_time" | "due_at";
};

export type CalendarEntry = {
  id: string;
  title: string;
  timing_kind: "timed" | "anytime";
  scheduled_date: string | null;
  start_time: string | null;
  end_time: string | null;
  timezone: string;
  participants: string[];
  reminder: Reminder | null;
  status: "scheduled" | "completed" | "cancelled";
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskItem = {
  id: string;
  title: string;
  due_at: string | null;
  timezone: string;
  reminder: Reminder | null;
  status: "open" | "completed" | "cancelled";
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
};

export type SchedulePage<T> = {
  items: T[];
  next_cursor: string | null;
};

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
