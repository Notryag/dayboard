import {
  completeCalendarEntry,
  completeTaskItem,
  reopenCalendarEntry,
  reopenTaskItem,
} from "./api";
import { getMessage, type Locale } from "@/i18n";
import { scheduleItemTitle } from "./scheduleItemPresentation";
import type { ScheduleChange, ScheduleDisplayItem } from "./types";

export async function completeScheduleItem(item: ScheduleDisplayItem, locale: Locale = "zh-CN"): Promise<ScheduleChange> {
  if (item.kind === "calendar") {
    const completed = await completeCalendarEntry(item.value);
    return {
      undo: {
        label: getMessage(locale, "schedule.completedItem", { title: scheduleItemTitle(item) }),
        run: async () => { await reopenCalendarEntry(completed); },
      },
    };
  }
  const completed = await completeTaskItem(item.value);
  return {
    undo: {
      label: getMessage(locale, "schedule.completedItem", { title: scheduleItemTitle(item) }),
      run: async () => { await reopenTaskItem(completed); },
    },
  };
}

export async function reopenScheduleItem(item: ScheduleDisplayItem, locale: Locale = "zh-CN"): Promise<ScheduleChange> {
  if (item.kind === "calendar") {
    const reopened = await reopenCalendarEntry(item.value);
    return {
      undo: {
        label: getMessage(locale, "schedule.reopenedItem", { title: scheduleItemTitle(item) }),
        run: async () => { await completeCalendarEntry(reopened); },
      },
    };
  }
  const reopened = await reopenTaskItem(item.value);
  return {
    undo: {
      label: getMessage(locale, "schedule.reopenedItem", { title: scheduleItemTitle(item) }),
      run: async () => { await completeTaskItem(reopened); },
    },
  };
}
