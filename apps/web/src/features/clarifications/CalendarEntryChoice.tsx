import type { CalendarEntryChoiceInteraction } from "./types";
import styles from "./clarifications.module.css";

type CalendarEntryChoiceProps = {
  interaction: CalendarEntryChoiceInteraction;
  disabled?: boolean;
  onSelect: (optionKey: string) => void;
};

function formatOptionTime(
  startTime?: string | null,
  timezone?: string | null,
  scheduledDate?: string | null,
) {
  if (!startTime) return scheduledDate ? `${scheduledDate} · 随时` : "随时";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone ?? undefined,
  }).format(new Date(startTime));
}

export function CalendarEntryChoice({
  interaction,
  disabled = false,
  onSelect,
}: CalendarEntryChoiceProps) {
  return (
    <div className={styles.options} role="group" aria-label="可选日程">
      {interaction.options.map((option) => (
        <button
          className={styles.option}
          disabled={disabled}
          key={option.key}
          onClick={() => onSelect(option.key)}
          type="button"
        >
          <span className={styles.optionTitle}>{option.title}</span>
          <span className={styles.optionTime}>
            {formatOptionTime(option.start_time, option.timezone, option.scheduled_date)}
          </span>
        </button>
      ))}
    </div>
  );
}
