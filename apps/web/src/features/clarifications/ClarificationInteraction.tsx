import { CalendarEntryChoice } from "./CalendarEntryChoice";
import { ChoiceOptions } from "./ChoiceOptions";
import type { ClarificationInteraction as Interaction } from "./types";

type ClarificationInteractionProps = {
  interaction: Interaction;
  disabled?: boolean;
  onSelect: (optionKey: string) => void;
};

export function ClarificationInteraction({
  interaction,
  disabled = false,
  onSelect,
}: ClarificationInteractionProps) {
  if (interaction.type === "calendar_entry_choice") {
    return (
      <CalendarEntryChoice
        disabled={disabled}
        interaction={interaction}
        onSelect={onSelect}
      />
    );
  }
  return (
    <ChoiceOptions
      disabled={disabled}
      options={interaction.type === "task_item_choice"
        ? interaction.options.map((option) => ({ key: option.key, label: option.title }))
        : interaction.options}
      onSelect={onSelect}
    />
  );
}
