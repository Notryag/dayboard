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

export async function reopenScheduleItem(item: ScheduleDisplayItem): Promise<ScheduleChange> {
  if (item.kind === "calendar") {
    const reopened = await reopenCalendarEntry(item.value);
    return {
      undo: {
        label: `已将“${scheduleItemTitle(item)}”标记为未完成`,
        run: async () => { await completeCalendarEntry(reopened); },
      },
    };
  }
  const reopened = await reopenTaskItem(item.value);
  return {
    undo: {
      label: `已将“${scheduleItemTitle(item)}”标记为未完成`,
      run: async () => { await completeTaskItem(reopened); },
    },
  };
}
