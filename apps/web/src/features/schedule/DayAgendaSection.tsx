"use client";

import { useMemo } from "react";
import { ChevronDown, Clock3, LoaderCircle, RotateCw } from "lucide-react";
import { formatScheduleTime } from "./date";
import { ScheduleItem } from "./ScheduleItem";
import type { CalendarEntry, ScheduleChange, TaskItem } from "./types";
import type { SchedulePageResource } from "./useSchedulePage";
import type { ReminderFocusTarget } from "@/features/reminders/types";
import styles from "./schedule.module.css";

type DayAgendaSectionProps = {
  calendar: SchedulePageResource<CalendarEntry>;
  focusTarget: ReminderFocusTarget | null;
  onChanged: (change?: ScheduleChange) => void;
  tasks: SchedulePageResource<TaskItem>;
  timezone: string;
};

type AgendaItem =
  | { entry: CalendarEntry; id: string; kind: "calendar"; label: string; sortKey: string }
  | { id: string; kind: "task"; label: string; sortKey: string; task: TaskItem };

function RetryNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.sourceError} role="status">
      <span>{message}</span>
      <button aria-label="重试" onClick={onRetry} title="重试" type="button">
        <RotateCw size={15} />
      </button>
    </div>
  );
}

export function DayAgendaSection({
  calendar,
  focusTarget,
  onChanged,
  tasks,
  timezone,
}: DayAgendaSectionProps) {
  const items = useMemo<AgendaItem[]>(() => {
    const calendarItems: AgendaItem[] = calendar.items.map((entry) => ({
      entry,
      id: `calendar-${entry.id}`,
      kind: "calendar",
      label: entry.start_time ? formatScheduleTime(entry.start_time, timezone) : "随时",
      sortKey: entry.start_time ?? `${entry.scheduled_date}T00:00:00`,
    }));
    const taskItems: AgendaItem[] = tasks.items.flatMap((task) =>
      task.due_at
        ? [{ id: `task-${task.id}`, kind: "task" as const, label: formatScheduleTime(task.due_at, timezone), sortKey: task.due_at, task }]
        : [],
    );
    return [...calendarItems, ...taskItems].sort((left, right) => {
      const timeDifference = Date.parse(left.sortKey) - Date.parse(right.sortKey);
      if (timeDifference !== 0) return timeDifference;
      return left.kind.localeCompare(right.kind);
    });
  }, [calendar.items, tasks.items, timezone]);

  const loadingWithoutItems = !items.length && (calendar.loading || tasks.loading);
  const hasErrors = Boolean(calendar.error || tasks.error);
  const hasMore = Boolean(calendar.cursor || tasks.cursor);

  return (
    <section
      aria-busy={calendar.loading || tasks.loading}
      aria-labelledby="day-agenda-heading"
      className={styles.section}
    >
      <div className={styles.sectionHeader}>
        <div className={`${styles.sectionTitle} ${styles.agendaSectionTitle}`}>
          <Clock3 aria-hidden="true" size={18} />
          <h3 id="day-agenda-heading">当天安排</h3>
        </div>
        {!loadingWithoutItems && !hasErrors ? (
          <span>{`${items.length}${hasMore ? "+" : ""} 项`}</span>
        ) : null}
      </div>

      {loadingWithoutItems ? (
        <div className={styles.notice} role="status">
          <LoaderCircle className={styles.spinner} size={20} />
          <p>正在加载当天安排</p>
        </div>
      ) : null}

      {!loadingWithoutItems && !items.length && !hasErrors ? (
        <p className={styles.empty}>这一天还没有安排</p>
      ) : null}

      {items.length ? (
        <ol className={styles.agendaList}>
          {items.map((item) => (
            <li key={item.id}>
              <time dateTime={item.sortKey}>{item.label}</time>
              <ScheduleItem
                highlighted={
                  focusTarget?.sourceId === (item.kind === "calendar" ? item.entry.id : item.task.id)
                }
                item={
                  item.kind === "calendar"
                    ? { kind: "calendar", value: item.entry }
                    : { kind: "task", value: item.task }
                }
                onChanged={onChanged}
                timezone={timezone}
                variant="agenda"
              />
            </li>
          ))}
        </ol>
      ) : null}

      {calendar.error ? <RetryNotice message={calendar.error} onRetry={calendar.retry} /> : null}
      {tasks.error ? <RetryNotice message={tasks.error} onRetry={tasks.retry} /> : null}

      {calendar.cursor ? (
        <button
          className={styles.moreButton}
          disabled={calendar.loading}
          onClick={calendar.loadMore}
          type="button"
        >
          {calendar.loading ? (
            <LoaderCircle className={styles.spinner} size={16} />
          ) : (
            <ChevronDown size={16} />
          )}
          {calendar.loading ? "正在加载" : "更多日程"}
        </button>
      ) : null}
      {tasks.cursor ? (
        <button
          className={styles.moreButton}
          disabled={tasks.loading}
          onClick={tasks.loadMore}
          type="button"
        >
          {tasks.loading ? (
            <LoaderCircle className={styles.spinner} size={16} />
          ) : (
            <ChevronDown size={16} />
          )}
          {tasks.loading ? "正在加载" : "更多待办"}
        </button>
      ) : null}
    </section>
  );
}
