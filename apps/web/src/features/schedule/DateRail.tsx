"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  dateRangeAround,
  formatAccessibleDate,
  formatDayNumber,
  formatRailWeekday,
  shiftDateKey,
} from "./date";
import styles from "./schedule.module.css";

type DateRailProps = {
  onSelectDate: (date: string) => void;
  selectedDate: string;
  today: string;
};

export function DateRail({ onSelectDate, selectedDate, today }: DateRailProps) {
  const hasCenteredRef = useRef(false);
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const dates = useMemo(() => dateRangeAround(selectedDate), [selectedDate]);
  const selectedMonth = selectedDate.slice(0, 7);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      selectedRef.current?.scrollIntoView({
        behavior: reduceMotion || !hasCenteredRef.current ? "auto" : "smooth",
        block: "nearest",
        inline: "center",
      });
      hasCenteredRef.current = true;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selectedDate]);

  return (
    <nav className={styles.dateRail} aria-label="浏览日期">
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
              onSelectDate(shiftDateKey(date, event.key === "ArrowLeft" ? -1 : 1));
            }}
            ref={isSelected ? selectedRef : null}
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
