import { getMessage, useI18n } from "@/i18n";
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
  locale: "zh-CN" | "en-US" = "zh-CN",
  anytimeLabel = getMessage(locale, "schedule.anytime"),
) {
  if (!startTime) return scheduledDate ? `${scheduledDate} · ${anytimeLabel}` : anytimeLabel;
  return new Intl.DateTimeFormat(locale, {
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
  const { locale, t } = useI18n();
  return (
    <div className={styles.options} role="group" aria-label={t("schedule.calendar")}>
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
            {formatOptionTime(option.start_time, option.timezone, option.scheduled_date, locale, t("schedule.anytime"))}
          </span>
        </button>
      ))}
    </div>
  );
}
