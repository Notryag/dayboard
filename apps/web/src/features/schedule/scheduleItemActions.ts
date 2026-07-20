import {
  completeCalendarEntry,
  completeTaskItem,
  reopenCalendarEntry,
  reopenTaskItem,
} from "./api";
import { scheduleItemTitle } from "./scheduleItemPresentation";
import type { ScheduleChange, ScheduleDisplayItem } from "./types";

export async function completeScheduleItem(item: ScheduleDisplayItem): Promise<ScheduleChange> {
  if (item.kind === "calendar") {
    const completed = await completeCalendarEntry(item.value);
    return {
      undo: {
        label: `已完成“${scheduleItemTitle(item)}”`,
        run: async () => { await reopenCalendarEntry(completed); },
      },
    };
  }
  const completed = await completeTaskItem(item.value);
  return {
    undo: {
      label: `已完成“${scheduleItemTitle(item)}”`,
      run: async () => { await reopenTaskItem(completed); },
    },
  };
}
