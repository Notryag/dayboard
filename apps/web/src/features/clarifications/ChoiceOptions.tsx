import { useI18n } from "@/i18n";
import styles from "./clarifications.module.css";

type ChoiceOptionsProps = {
  options: { key: string; label: string }[];
  disabled?: boolean;
  onSelect: (optionKey: string) => void;
};

export function ChoiceOptions({
  options,
  disabled = false,
  onSelect,
}: ChoiceOptionsProps) {
  const { t } = useI18n();
  return (
    <div className={styles.options} role="group" aria-label={t("common.more")}>
      {options.map((option) => (
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
