"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DateRail } from "./DateRail";
import { DayAgendaSection } from "./DayAgendaSection";
import { ScheduleHeader } from "./ScheduleHeader";
import { TaskListSection } from "./TaskListSection";
import { getCalendarEntryPage, getDatedTaskPage, getUndatedTaskPage } from "./api";
import { dateKeyInTimezone } from "./date";
import type { CalendarEntry, TaskItem } from "./types";
import { useSchedulePage } from "./useSchedulePage";
import styles from "./schedule.module.css";

type ScheduleInspectorProps = {
  onClose: () => void;
  timezone: string;
};

const headingId = "schedule-heading";

export function ScheduleInspector({ onClose, timezone }: ScheduleInspectorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const today = dateKeyInTimezone(new Date(), timezone);
  const [selectedDate, setSelectedDate] = useState(today);

  const loadCalendarPage = useCallback(
    (cursor?: string, signal?: AbortSignal) =>
      getCalendarEntryPage(selectedDate, cursor, signal),
    [selectedDate],
  );
  const loadDatedTaskPage = useCallback(
    (cursor?: string, signal?: AbortSignal) =>
      getDatedTaskPage(selectedDate, cursor, signal),
    [selectedDate],
  );
  const loadUndatedTaskPage = useCallback(
    (cursor?: string, signal?: AbortSignal) => getUndatedTaskPage(cursor, signal),
    [],
  );

  const calendar = useSchedulePage<CalendarEntry>({
    loadErrorMessage: "暂时无法加载日程",
    loadMoreErrorMessage: "暂时无法加载更多日程",
    loadPage: loadCalendarPage,
  });
  const datedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载当天待办",
    loadMoreErrorMessage: "暂时无法加载更多当天待办",
    loadPage: loadDatedTaskPage,
  });
  const undatedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载待办",
    loadMoreErrorMessage: "暂时无法加载更多待办",
    loadPage: loadUndatedTaskPage,
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
      dialog.focus({ preventScroll: true });
    }
  }, []);

  return (
    <dialog
      aria-labelledby={headingId}
      className={styles.dialog}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      ref={dialogRef}
      tabIndex={-1}
    >
      <ScheduleHeader
        headingId={headingId}
        onClose={onClose}
        onSelectDate={setSelectedDate}
        selectedDate={selectedDate}
      />
      <DateRail onSelectDate={setSelectedDate} selectedDate={selectedDate} today={today} />

      <div className={styles.content} aria-live="polite">
        <DayAgendaSection calendar={calendar} tasks={datedTasks} timezone={timezone} />
        <TaskListSection
          emptyText="没有未安排时间的待办"
          id="undated-task-section"
          resource={undatedTasks}
          title="未排时间"
        />
      </div>
    </dialog>
  );
}
