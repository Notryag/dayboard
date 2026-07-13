"use client";

import { ChevronDown, Circle, ListTodo, LoaderCircle, RotateCw } from "lucide-react";
import type { TaskItem } from "./types";
import styles from "./schedule.module.css";

type TaskListSectionProps = {
  cursor: string | null;
  emptyText: string;
  error: string | null;
  id: string;
  loading: boolean;
  onLoadMore: () => void;
  onRetry: () => void;
  showDueTime?: boolean;
  tasks: TaskItem[];
  timezone: string;
  title: string;
};

function formatTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone,
  }).format(new Date(value));
}

export function TaskListSection({
  cursor,
  emptyText,
  error,
  id,
  loading,
  onLoadMore,
  onRetry,
  showDueTime = false,
  tasks,
  timezone,
  title,
}: TaskListSectionProps) {
  const headingId = `${id}-heading`;

  return (
    <section className={styles.section} aria-labelledby={headingId}>
      <div className={styles.sectionHeader}>
        <div className={`${styles.sectionTitle} ${styles.taskSectionTitle}`}>
          <ListTodo size={18} aria-hidden="true" />
          <h3 id={headingId}>{title}</h3>
        </div>
        {!loading && !error ? (
          <span>{`${tasks.length}${cursor ? "+" : ""} 项`}</span>
        ) : null}
      </div>

      {error && !tasks.length ? (
        <div className={styles.notice} role="status">
          <p>{error}</p>
          <button type="button" onClick={onRetry}>
            <RotateCw size={16} />
            重试
          </button>
        </div>
      ) : null}
      {loading && !tasks.length ? (
        <div className={styles.notice} role="status">
          <LoaderCircle className={styles.spinner} size={20} />
          <p>正在加载待办</p>
        </div>
      ) : null}
      {!loading && !error && !tasks.length ? <p className={styles.empty}>{emptyText}</p> : null}
      {tasks.length ? (
        <ul className={styles.taskList}>
          {tasks.map((task) => (
            <li key={task.id}>
              <Circle size={17} aria-hidden="true" />
              <div className={styles.taskBody}>
                <strong>{task.title}</strong>
                {showDueTime && task.due_at ? (
                  <time dateTime={task.due_at}>{formatTime(task.due_at, timezone)}</time>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {error && tasks.length ? <p className={styles.inlineError}>{error}</p> : null}
      {cursor ? (
        <button
          className={styles.moreButton}
          disabled={loading}
          onClick={onLoadMore}
          type="button"
        >
          {loading ? <LoaderCircle className={styles.spinner} size={16} /> : <ChevronDown size={16} />}
          {loading ? "正在加载" : "更多待办"}
        </button>
      ) : null}
    </section>
  );
}
