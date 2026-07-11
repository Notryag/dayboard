import type { SuggestedChoiceInteraction } from "./types";
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
  return (
    <div className={styles.options} role="group" aria-label="建议选项">
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
