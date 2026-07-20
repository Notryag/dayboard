"use client";

import { ChevronDown } from "lucide-react";
import { formatMonthYear, formatSelectedWeekday } from "./date";
import styles from "./schedule.module.css";

type ScheduleHeaderProps = {
  headingId: string;
  onJumpToDate: (date: string) => void;
  selectedDate: string;
};

export function ScheduleHeader({
  headingId,
  onJumpToDate,
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
              if (event.target.value) onJumpToDate(event.target.value);
            }}
            type="date"
            value={selectedDate}
          />
        </label>
      </div>
    </header>
  );
}
