"use client";

import { ChevronDown, X } from "lucide-react";
import { formatMonthYear, formatSelectedWeekday } from "./date";
import styles from "./schedule.module.css";

type ScheduleHeaderProps = {
  headingId: string;
  onClose: () => void;
  onSelectDate: (date: string) => void;
  selectedDate: string;
};

export function ScheduleHeader({
  headingId,
  onClose,
  onSelectDate,
  selectedDate,
}: ScheduleHeaderProps) {
  return (
    <header className={styles.header}>
      <h2 id={headingId}>{formatSelectedWeekday(selectedDate)}</h2>
      <div className={styles.headerActions}>
        <label className={styles.monthPicker}>
          <span>{formatMonthYear(selectedDate)}</span>
          <ChevronDown aria-hidden="true" size={16} />
          <input
            aria-label="跳转日期"
            onChange={(event) => {
              if (event.target.value) onSelectDate(event.target.value);
            }}
            type="date"
            value={selectedDate}
          />
        </label>
        <button
          aria-label="关闭"
          className={styles.iconButton}
          onClick={onClose}
          title="关闭"
          type="button"
        >
          <X size={20} />
        </button>
      </div>
    </header>
  );
}
