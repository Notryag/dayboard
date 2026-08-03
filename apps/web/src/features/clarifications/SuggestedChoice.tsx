import type { SuggestedChoiceInteraction } from "./types";
import { useI18n } from "@/i18n";
import styles from "./clarifications.module.css";

type SuggestedChoiceProps = {
  interaction: SuggestedChoiceInteraction;
  disabled?: boolean;
  onSelect: (optionKey: string) => void;
};

export function SuggestedChoice({
  interaction,
  disabled = false,
  onSelect,
}: SuggestedChoiceProps) {
  const { t } = useI18n();
  return (
    <div className={styles.options} role="group" aria-label={t("common.more")}>
      {interaction.options.map((option) => (
        <button
          className={styles.option}
          disabled={disabled}
          key={option.key}
          onClick={() => onSelect(option.key)}
          type="button"
        >
          <span className={styles.optionTitle}>{option.label}</span>
        </button>
      ))}
    </div>
  );
}
