"use client";

import { useCallback, useState } from "react";
import { DateRail } from "./DateRail";
import { DayAgendaSection } from "./DayAgendaSection";
import { ScheduleHeader } from "./ScheduleHeader";
import { TaskListSection } from "./TaskListSection";
import { getCalendarEntryPage, getDatedTaskPage, getUndatedTaskPage } from "./api";
import { dateKeyInTimezone } from "./date";
import type { CalendarEntry, ScheduleChange, TaskItem } from "./types";
import { useSchedulePage } from "./useSchedulePage";
import styles from "./schedule.module.css";

type SchedulePanelProps = {
  accountName: string;
  active: boolean;
  onChanged: (change?: ScheduleChange) => void;
  onLogout: () => void;
  refreshKey: number;
  timezone: string;
};

const headingId = "schedule-heading";

export function SchedulePanel({
  accountName,
  active,
  onChanged,
  onLogout,
  refreshKey,
  timezone,
}: SchedulePanelProps) {
  const today = dateKeyInTimezone(new Date(), timezone);
  const [selectedDate, setSelectedDate] = useState(today);
  const [dateRailCenter, setDateRailCenter] = useState(today);

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
    reloadKey: refreshKey,
  });
  const datedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载当天待办",
    loadMoreErrorMessage: "暂时无法加载更多当天待办",
    loadPage: loadDatedTaskPage,
    reloadKey: refreshKey,
  });
  const undatedTasks = useSchedulePage<TaskItem>({
    loadErrorMessage: "暂时无法加载待办",
    loadMoreErrorMessage: "暂时无法加载更多待办",
    loadPage: loadUndatedTaskPage,
    reloadKey: refreshKey,
  });

  const jumpToDate = useCallback((date: string) => {
    setSelectedDate(date);
    setDateRailCenter(date);
  }, []);

  return (
    <section aria-labelledby={headingId} className={styles.panel}>
      <ScheduleHeader
        accountName={accountName}
        headingId={headingId}
        onJumpToDate={jumpToDate}
        onLogout={onLogout}
        selectedDate={selectedDate}
        timezone={timezone}
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
