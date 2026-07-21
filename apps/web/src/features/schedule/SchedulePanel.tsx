"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DateRail } from "./DateRail";
import { DayAgendaSection } from "./DayAgendaSection";
import { ScheduleHeader } from "./ScheduleHeader";
import { TaskListSection } from "./TaskListSection";
import { getCalendarEntryPage, getDatedTaskPage, getUndatedTaskPage } from "./api";
import { dateKeyInTimezone } from "./date";
import type { CalendarEntry, ScheduleChange, TaskItem } from "./types";
import type { ReminderFocusTarget } from "@/features/reminders/types";
import { useSchedulePage } from "./useSchedulePage";
import styles from "./schedule.module.css";

type SchedulePanelProps = {
  active: boolean;
  focusTarget: ReminderFocusTarget | null;
  onChanged: (change?: ScheduleChange) => void;
  refreshKey: number;
  timezone: string;
};

const headingId = "schedule-heading";

export function SchedulePanel({
  active,
  focusTarget,
  onChanged,
  refreshKey,
  timezone,
}: SchedulePanelProps) {
  const today = dateKeyInTimezone(new Date(), timezone);
  const queryClient = useQueryClient();
  const previousRefreshKey = useRef(refreshKey);
  const initialDate = focusTarget?.date ?? today;
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [dateRailCenter, setDateRailCenter] = useState(initialDate);

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
    queryKey: ["schedule", "calendar", selectedDate],
  });
  const datedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载当天待办",
    loadMoreErrorMessage: "暂时无法加载更多当天待办",
    loadPage: loadDatedTaskPage,
    queryKey: ["schedule", "tasks", "dated", selectedDate],
  });
  const undatedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载待办",
    loadMoreErrorMessage: "暂时无法加载更多待办",
    loadPage: loadUndatedTaskPage,
    queryKey: ["schedule", "tasks", "undated"],
  });

  useEffect(() => {
    if (previousRefreshKey.current === refreshKey) return;
    previousRefreshKey.current = refreshKey;
    void queryClient.invalidateQueries({ queryKey: ["schedule"] });
  }, [queryClient, refreshKey]);

  const jumpToDate = useCallback((date: string) => {
    setSelectedDate(date);
    setDateRailCenter(date);
  }, []);

  return (
    <section aria-labelledby={headingId} className={styles.panel}>
      <ScheduleHeader
        headingId={headingId}
        onJumpToDate={jumpToDate}
        selectedDate={selectedDate}
      />
      <DateRail
        active={active}
        centerDate={dateRailCenter}
        onCenterDate={setDateRailCenter}
        onSelectDate={setSelectedDate}
        selectedDate={selectedDate}
        today={today}
      />

      <div className={styles.content} aria-live="polite">
        <DayAgendaSection
          calendar={calendar}
          focusTarget={focusTarget}
          onChanged={onChanged}
          tasks={datedTasks}
          timezone={timezone}
        />
        <TaskListSection
          emptyText="没有待办"
          id="undated-task-section"
          onChanged={onChanged}
          resource={undatedTasks}
          title="待办清单"
        />
      </div>
    </section>
  );
}
