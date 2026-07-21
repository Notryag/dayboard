export type ReminderFocusTarget = {
  date: string;
  requestId: number;
  sourceId: string;
  sourceType: "calendar_entry" | "task_item";
};
