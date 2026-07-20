export type Reminder = {
  offset: string;
  anchor: "start_time" | "due_at";
};

export type CalendarEntry = {
  id: string;
  title: string;
  start_time: string;
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

export type RunScheduleItemGroup = {
  run_id: string;
  calendar_entries: CalendarEntry[];
  task_items: TaskItem[];
};

export type ScheduleDisplayItem =
  | { kind: "calendar"; value: CalendarEntry }
  | { kind: "task"; value: TaskItem };

export type ScheduleChange = {
  undo?: {
    label: string;
    run: () => Promise<void>;
  };
};
