"use client";

import { ChevronDown, ListTodo, LoaderCircle, RotateCw } from "lucide-react";
import { ScheduleItem } from "./ScheduleItem";
import type { TaskItem } from "./types";
import type { SchedulePageResource } from "./useSchedulePage";
import styles from "./schedule.module.css";

type TaskListSectionProps = {
  emptyText: string;
  id: string;
  onChanged: () => void;
  resource: SchedulePageResource<TaskItem>;
  title: string;
};

export function TaskListSection({
  emptyText,
  id,
  onChanged,
  resource,
  title,
}: TaskListSectionProps) {
  const headingId = `${id}-heading`;
  const { cursor, error, items, loadMore, loading, retry } = resource;

  return (
    <section aria-busy={loading} className={styles.section} aria-labelledby={headingId}>
      <div className={styles.sectionHeader}>
        <div className={`${styles.sectionTitle} ${styles.taskSectionTitle}`}>
          <ListTodo size={18} aria-hidden="true" />
          <h3 id={headingId}>{title}</h3>
        </div>
        {!loading && !error ? (
          <span>{`${items.length}${cursor ? "+" : ""} 项`}</span>
        ) : null}
      </div>

      {error && !items.length ? (
        <div className={styles.notice} role="status">
          <p>{error}</p>
          <button type="button" onClick={retry}>
            <RotateCw size={16} />
            重试
          </button>
        </div>
      ) : null}
      {loading && !items.length ? (
        <div className={styles.notice} role="status">
          <LoaderCircle className={styles.spinner} size={20} />
          <p>正在加载待办</p>
        </div>
      ) : null}
      {!loading && !error && !items.length ? <p className={styles.empty}>{emptyText}</p> : null}
      {items.length ? (
        <ul className={styles.taskList}>
          {items.map((task) => (
            <li key={task.id}>
              <ScheduleItem
                item={{ kind: "task", value: task }}
                onChanged={onChanged}
                timezone={task.timezone}
                variant="task"
              />
            </li>
          ))}
        </ul>
      ) : null}
      {error && items.length ? <p className={styles.inlineError}>{error}</p> : null}
      {cursor ? (
        <button
          className={styles.moreButton}
          disabled={loading}
          onClick={loadMore}
          type="button"
        >
          {loading ? <LoaderCircle className={styles.spinner} size={16} /> : <ChevronDown size={16} />}
          {loading ? "正在加载" : "更多待办"}
        </button>
      ) : null}
    </section>
  );
}
