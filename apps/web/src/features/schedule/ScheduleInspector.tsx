"use client";

import { useEffect, useRef, useState } from "react";
import { CalendarClock, CheckSquare, X } from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { getSchedulePage } from "./api";
import type { CalendarEntry, ScheduleView, TaskItem } from "./types";
import styles from "./schedule.module.css";

type ScheduleInspectorProps = {
  onClose: () => void;
};

const views: Array<{ key: ScheduleView; label: string }> = [
  { key: "today", label: "今天" },
  { key: "tomorrow", label: "明天" },
  { key: "tasks", label: "任务" },
];

function formatTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone,
  }).format(new Date(value));
}

function isTask(item: CalendarEntry | TaskItem): item is TaskItem {
  return "status" in item;
}

export function ScheduleInspector({ onClose }: ScheduleInspectorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const [view, setView] = useState<ScheduleView>("today");
  const [items, setItems] = useState<Array<CalendarEntry | TaskItem>>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const controller = new AbortController();
    requestRef.current = controller;
    dialog.showModal();
    void getSchedulePage("today", undefined, controller.signal)
      .then((page) => {
        setItems(page.items);
        setCursor(page.next_cursor);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(userFacingApiError(caught, "暂时无法加载安排"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
        if (requestRef.current === controller) requestRef.current = null;
      });
    return () => {
      controller.abort();
      requestRef.current = null;
    };
  }, []);

  async function changeView(nextView: ScheduleView) {
    if (nextView === view) return;
    setView(nextView);
    setItems([]);
    setCursor(null);
    setError(null);
    setIsLoading(true);
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const page = await getSchedulePage(nextView, undefined, controller.signal);
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(userFacingApiError(caught, "暂时无法加载安排"));
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setIsLoading(false);
      }
    }
  }

  async function loadMore() {
    if (!cursor || isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      const page = await getSchedulePage(view, cursor);
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch (caught) {
      setError(userFacingApiError(caught, "暂时无法加载更多安排"));
    } finally {
      setIsLoading(false);
    }
  }

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
          <p>安排</p>
          <h2>我的日程与任务</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭" title="关闭">
          <X size={20} />
        </button>
      </div>

      <div className={styles.tabs} role="tablist" aria-label="安排视图">
        {views.map((candidate) => (
          <button
            aria-selected={view === candidate.key}
            key={candidate.key}
            onClick={() => void changeView(candidate.key)}
            role="tab"
            type="button"
          >
            {candidate.label}
          </button>
        ))}
      </div>

      <div className={styles.content} aria-live="polite">
        {error ? <p className={styles.notice}>{error}</p> : null}
        {!error && isLoading && !items.length ? (
          <p className={styles.notice}>正在加载</p>
        ) : null}
        {!error && !isLoading && !items.length ? (
          <p className={styles.notice}>{view === "tasks" ? "没有待办任务" : "没有安排"}</p>
        ) : null}
        {items.length ? (
          <ol className={styles.list}>
            {items.map((item) => (
              <li key={item.id}>
                <span className={styles.itemIcon} aria-hidden="true">
                  {isTask(item) ? <CheckSquare size={17} /> : <CalendarClock size={17} />}
                </span>
                <div>
                  <strong>{item.title}</strong>
                  <span>
                    {isTask(item)
                      ? item.due_at
                        ? `截止 ${formatTime(item.due_at, item.timezone)}`
                        : "无截止时间"
                      : `${formatTime(item.start_time, item.timezone)}${
                          item.end_time ? ` - ${formatTime(item.end_time, item.timezone)}` : ""
                        }`}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        ) : null}
      </div>

      {cursor ? (
        <button className={styles.moreButton} disabled={isLoading} onClick={loadMore} type="button">
          {isLoading ? "正在加载" : "加载更多"}
        </button>
      ) : null}
    </dialog>
  );
}
