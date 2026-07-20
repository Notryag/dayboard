"use client";

import { ChevronDown } from "lucide-react";
import { formatMonthYear, formatSelectedWeekday } from "./date";
import { ScheduleSettingsDrawer } from "./ScheduleSettingsDrawer";
import styles from "./schedule.module.css";

type ScheduleHeaderProps = {
  accountName: string;
  headingId: string;
  onJumpToDate: (date: string) => void;
  onLogout: () => void;
  selectedDate: string;
  timezone: string;
};

export function ScheduleHeader({
  accountName,
  headingId,
  onJumpToDate,
  onLogout,
  selectedDate,
  timezone,
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
        <ScheduleSettingsDrawer
          accountName={accountName}
          onLogout={onLogout}
          timezone={timezone}
        />
      </div>
    </header>
  );
}
