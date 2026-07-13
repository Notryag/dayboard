"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import {
  dateRangeAround,
  formatAccessibleDate,
  formatDayNumber,
  formatRailWeekday,
  shiftDateKey,
} from "./date";
import styles from "./schedule.module.css";

type DateRailProps = {
  centerDate: string;
  onCenterDate: (date: string) => void;
  onSelectDate: (date: string) => void;
  selectedDate: string;
  today: string;
};

export function DateRail({
  centerDate,
  onCenterDate,
  onSelectDate,
  selectedDate,
  today,
}: DateRailProps) {
  const railRef = useRef<HTMLElement>(null);
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const dates = useMemo(() => dateRangeAround(centerDate), [centerDate]);
  const selectedMonth = selectedDate.slice(0, 7);

  useLayoutEffect(() => {
    if (!railRef.current?.closest("dialog")?.open) return;
    selectedRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [centerDate]);

  return (
    <nav className={styles.dateRail} aria-label="浏览日期" ref={railRef}>
      {dates.map((date) => {
        const isSelected = date === selectedDate;
        const isToday = date === today;
        const isOutsideMonth = date.slice(0, 7) !== selectedMonth;
        return (
          <button
            aria-label={formatAccessibleDate(date)}
            aria-current={isSelected ? "date" : undefined}
            className={`${styles.dateCell} ${isSelected ? styles.dateCellSelected : ""} ${
              isToday && !isSelected ? styles.dateCellToday : ""
            } ${isOutsideMonth ? styles.dateCellOutsideMonth : ""}`}
            key={date}
            onClick={() => onSelectDate(date)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
              event.preventDefault();
              const nextDate = shiftDateKey(date, event.key === "ArrowLeft" ? -1 : 1);
              if (!dates.includes(nextDate)) onCenterDate(nextDate);
              onSelectDate(nextDate);
              window.requestAnimationFrame(() => {
                railRef.current
                  ?.querySelector<HTMLButtonElement>(`[data-date='${nextDate}']`)
                  ?.focus({ preventScroll: true });
              });
            }}
            ref={isSelected ? selectedRef : null}
            data-date={date}
            data-selected-date={isSelected ? "true" : undefined}
            type="button"
          >
            <span>{formatRailWeekday(date)}</span>
            <strong>{formatDayNumber(date)}</strong>
          </button>
        );
      })}
    </nav>
  );
}
