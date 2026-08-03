"use client";

import { ChevronDown } from "lucide-react";
import { useI18n } from "@/i18n";
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
  const { locale, t } = useI18n();
  return (
    <header className={styles.header}>
      <h2 id={headingId}>{formatSelectedWeekday(selectedDate, locale)}</h2>
      <div className={styles.headerActions}>
        <label className={styles.monthPicker}>
          <span>{formatMonthYear(selectedDate, locale)}</span>
          <ChevronDown aria-hidden="true" size={16} />
          <input
            aria-label={t("schedule.jumpToDate")}
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
