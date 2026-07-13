"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CalendarClock,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  RotateCw,
  X,
} from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { getCalendarEntryPage, getDatedTaskPage, getUndatedTaskPage } from "./api";
import { TaskListSection } from "./TaskListSection";
import type { CalendarEntry, TaskItem } from "./types";
import styles from "./schedule.module.css";

type ScheduleInspectorProps = {
  onClose: () => void;
  timezone: string;
};

function dateKeyInTimezone(value: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: timezone,
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function dateFromKey(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function shiftDateKey(value: string, amount: number) {
  const date = dateFromKey(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function formatDateHeading(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
    timeZone: "UTC",
  }).format(dateFromKey(value));
}

function formatTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone,
  }).format(new Date(value));
}

export function ScheduleInspector({ onClose, timezone }: ScheduleInspectorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const entryRequestRef = useRef<AbortController | null>(null);
  const datedTaskRequestRef = useRef<AbortController | null>(null);
  const undatedTaskRequestRef = useRef<AbortController | null>(null);
  const today = dateKeyInTimezone(new Date(), timezone);
  const [selectedDate, setSelectedDate] = useState(today);
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [entryCursor, setEntryCursor] = useState<string | null>(null);
  const [entriesLoading, setEntriesLoading] = useState(true);
  const [entriesError, setEntriesError] = useState<string | null>(null);
  const [datedTasks, setDatedTasks] = useState<TaskItem[]>([]);
  const [datedTaskCursor, setDatedTaskCursor] = useState<string | null>(null);
  const [datedTasksLoading, setDatedTasksLoading] = useState(true);
  const [datedTasksError, setDatedTasksError] = useState<string | null>(null);
  const [undatedTasks, setUndatedTasks] = useState<TaskItem[]>([]);
  const [undatedTaskCursor, setUndatedTaskCursor] = useState<string | null>(null);
  const [undatedTasksLoading, setUndatedTasksLoading] = useState(true);
  const [undatedTasksError, setUndatedTasksError] = useState<string | null>(null);

  function selectDate(date: string) {
    if (date === selectedDate) return;
    entryRequestRef.current?.abort();
    datedTaskRequestRef.current?.abort();
    setEntries([]);
    setEntryCursor(null);
    setEntriesError(null);
    setEntriesLoading(true);
    setDatedTasks([]);
    setDatedTaskCursor(null);
    setDatedTasksError(null);
    setDatedTasksLoading(true);
    setSelectedDate(date);
  }

  const loadEntries = useCallback(
    async (date: string, cursor?: string) => {
      const append = Boolean(cursor);
      entryRequestRef.current?.abort();
      const controller = new AbortController();
      entryRequestRef.current = controller;
      setEntriesLoading(true);
      setEntriesError(null);
      if (!append) {
        setEntries([]);
        setEntryCursor(null);
      }
      try {
        const page = await getCalendarEntryPage(date, cursor, controller.signal);
        setEntries((current) => (append ? [...current, ...page.items] : page.items));
        setEntryCursor(page.next_cursor);
      } catch (caught: unknown) {
        if (!controller.signal.aborted) {
          setEntriesError(
            userFacingApiError(caught, append ? "暂时无法加载更多日程" : "暂时无法加载日程"),
          );
        }
      } finally {
        if (entryRequestRef.current === controller) {
          entryRequestRef.current = null;
          setEntriesLoading(false);
        }
      }
    },
    [],
  );

  const loadDatedTasks = useCallback(async (date: string, cursor?: string) => {
    const append = Boolean(cursor);
    datedTaskRequestRef.current?.abort();
    const controller = new AbortController();
    datedTaskRequestRef.current = controller;
    setDatedTasksLoading(true);
    setDatedTasksError(null);
    if (!append) {
      setDatedTasks([]);
      setDatedTaskCursor(null);
    }
    try {
      const page = await getDatedTaskPage(date, cursor, controller.signal);
      setDatedTasks((current) => (append ? [...current, ...page.items] : page.items));
      setDatedTaskCursor(page.next_cursor);
    } catch (caught: unknown) {
      if (!controller.signal.aborted) {
        setDatedTasksError(
          userFacingApiError(
            caught,
            append ? "暂时无法加载更多当天待办" : "暂时无法加载当天待办",
          ),
        );
      }
    } finally {
      if (datedTaskRequestRef.current === controller) {
        datedTaskRequestRef.current = null;
        setDatedTasksLoading(false);
      }
    }
  }, []);

  const loadUndatedTasks = useCallback(async (cursor?: string) => {
    const append = Boolean(cursor);
    undatedTaskRequestRef.current?.abort();
    const controller = new AbortController();
    undatedTaskRequestRef.current = controller;
    setUndatedTasksLoading(true);
    setUndatedTasksError(null);
    if (!append) {
      setUndatedTasks([]);
      setUndatedTaskCursor(null);
    }
    try {
      const page = await getUndatedTaskPage(cursor, controller.signal);
      setUndatedTasks((current) => (append ? [...current, ...page.items] : page.items));
      setUndatedTaskCursor(page.next_cursor);
    } catch (caught: unknown) {
      if (!controller.signal.aborted) {
        setUndatedTasksError(
          userFacingApiError(caught, append ? "暂时无法加载更多待办" : "暂时无法加载待办"),
        );
      }
    } finally {
      if (undatedTaskRequestRef.current === controller) {
        undatedTaskRequestRef.current = null;
        setUndatedTasksLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    entryRequestRef.current = controller;
    void getCalendarEntryPage(selectedDate, undefined, controller.signal)
      .then((page) => {
        setEntries(page.items);
        setEntryCursor(page.next_cursor);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setEntriesError(userFacingApiError(caught, "暂时无法加载日程"));
        }
      })
      .finally(() => {
        if (entryRequestRef.current === controller) {
          entryRequestRef.current = null;
          setEntriesLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedDate]);

  useEffect(() => {
    const controller = new AbortController();
    datedTaskRequestRef.current = controller;
    void getDatedTaskPage(selectedDate, undefined, controller.signal)
      .then((page) => {
        setDatedTasks(page.items);
        setDatedTaskCursor(page.next_cursor);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setDatedTasksError(userFacingApiError(caught, "暂时无法加载当天待办"));
        }
      })
      .finally(() => {
        if (datedTaskRequestRef.current === controller) {
          datedTaskRequestRef.current = null;
          setDatedTasksLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedDate]);

  useEffect(() => {
    const controller = new AbortController();
    undatedTaskRequestRef.current = controller;
    void getUndatedTaskPage(undefined, controller.signal)
      .then((page) => {
        setUndatedTasks(page.items);
        setUndatedTaskCursor(page.next_cursor);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setUndatedTasksError(userFacingApiError(caught, "暂时无法加载待办"));
        }
      })
      .finally(() => {
        if (undatedTaskRequestRef.current === controller) {
          undatedTaskRequestRef.current = null;
          setUndatedTasksLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(
    () => () => {
      entryRequestRef.current?.abort();
      datedTaskRequestRef.current?.abort();
      undatedTaskRequestRef.current?.abort();
    },
    [],
  );

  return (
    <dialog
      className={styles.dialog}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      ref={dialogRef}
    >
      <div className={styles.header}>
        <div>
          <p>日视图</p>
          <h2>{formatDateHeading(selectedDate)}</h2>
        </div>
        <button className={styles.iconButton} type="button" onClick={onClose} aria-label="关闭" title="关闭">
          <X size={20} />
        </button>
      </div>

      <nav className={styles.dateNavigation} aria-label="选择日期">
        <button
          className={styles.iconButton}
          type="button"
          onClick={() => selectDate(shiftDateKey(selectedDate, -1))}
          aria-label="前一天"
          title="前一天"
        >
          <ChevronLeft size={20} />
        </button>
        <input
          className={styles.dateInput}
          type="date"
          value={selectedDate}
          onChange={(event) => {
            if (event.target.value) selectDate(event.target.value);
          }}
          aria-label="日期"
        />
        <button
          className={styles.todayButton}
          type="button"
          disabled={selectedDate === today}
          onClick={() => selectDate(today)}
        >
          今天
        </button>
        <button
          className={styles.iconButton}
          type="button"
          onClick={() => selectDate(shiftDateKey(selectedDate, 1))}
          aria-label="后一天"
          title="后一天"
        >
          <ChevronRight size={20} />
        </button>
      </nav>

      <div className={styles.content} aria-live="polite">
        <section className={styles.section} aria-labelledby="calendar-section-heading">
          <div className={styles.sectionHeader}>
            <div className={styles.sectionTitle}>
              <CalendarClock size={18} aria-hidden="true" />
              <h3 id="calendar-section-heading">日程</h3>
            </div>
            {!entriesLoading && !entriesError ? (
              <span>{`${entries.length}${entryCursor ? "+" : ""} 项`}</span>
            ) : null}
          </div>

          {entriesError && !entries.length ? (
            <div className={styles.notice} role="status">
              <p>{entriesError}</p>
              <button type="button" onClick={() => void loadEntries(selectedDate)}>
                <RotateCw size={16} />
                重试
              </button>
            </div>
          ) : null}
          {entriesLoading && !entries.length ? (
            <div className={styles.notice} role="status">
              <LoaderCircle className={styles.spinner} size={20} />
              <p>正在加载日程</p>
            </div>
          ) : null}
          {!entriesLoading && !entriesError && !entries.length ? (
            <p className={styles.empty}>这一天还没有日程</p>
          ) : null}
          {entries.length ? (
            <ol className={styles.timeline}>
              {entries.map((entry) => (
                <li key={entry.id}>
                  <time dateTime={entry.start_time}>{formatTime(entry.start_time, timezone)}</time>
                  <span className={styles.timelineTrack} aria-hidden="true">
                    <span />
                  </span>
                  <div className={styles.eventBody}>
                    <strong>{entry.title}</strong>
                    <p>
                      {entry.end_time
                        ? `至 ${formatTime(entry.end_time, timezone)}`
                        : "未设置结束时间"}
                      {entry.participants.length
                        ? ` · ${entry.participants.length} 位参与者`
                        : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          ) : null}
          {entriesError && entries.length ? <p className={styles.inlineError}>{entriesError}</p> : null}
          {entryCursor ? (
            <button
              className={styles.moreButton}
              disabled={entriesLoading}
              onClick={() => void loadEntries(selectedDate, entryCursor)}
              type="button"
            >
              {entriesLoading ? <LoaderCircle className={styles.spinner} size={16} /> : <ChevronDown size={16} />}
              {entriesLoading ? "正在加载" : "更多日程"}
            </button>
          ) : null}
        </section>

        <TaskListSection
          cursor={datedTaskCursor}
          emptyText="这一天还没有待办"
          error={datedTasksError}
          id="dated-task-section"
          loading={datedTasksLoading}
          onLoadMore={() => void loadDatedTasks(selectedDate, datedTaskCursor ?? undefined)}
          onRetry={() => void loadDatedTasks(selectedDate)}
          showDueTime
          tasks={datedTasks}
          timezone={timezone}
          title="当天待办"
        />

        <TaskListSection
          cursor={undatedTaskCursor}
          emptyText="没有未安排时间的待办"
          error={undatedTasksError}
          id="undated-task-section"
          loading={undatedTasksLoading}
          onLoadMore={() => void loadUndatedTasks(undatedTaskCursor ?? undefined)}
          onRetry={() => void loadUndatedTasks()}
          tasks={undatedTasks}
          timezone={timezone}
          title="未排时间"
        />
      </div>
    </dialog>
  );
}
