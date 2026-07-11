import { CalendarEntryChoice } from "./CalendarEntryChoice";
import { SuggestedChoice } from "./SuggestedChoice";
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
    <SuggestedChoice disabled={disabled} interaction={interaction} onSelect={onSelect} />
  );
}
