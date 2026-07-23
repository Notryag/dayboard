import type { ClarificationChoice, ConversationState } from "@/lib/api/types";

export type { ConversationState };

export type ClarificationInteraction = NonNullable<
  ConversationState["interaction"]["payload"]["presentation"]
>;
export type CalendarEntryChoiceInteraction = Extract<
  ClarificationInteraction,
  { type: "calendar_entry_choice" }
>;
export type SuggestedChoiceInteraction = Extract<
  ClarificationInteraction,
  { type: "suggested_choice" }
>;

export type ClarificationChoiceResponse = ClarificationChoice;

export function clarificationPresentation(
  state: ConversationState | null,
): ClarificationInteraction | null {
  if (
    !state
    || state.interaction.interaction_type !== "dayboard.clarification"
    || state.interaction.schema_version !== 1
  ) {
    return null;
  }
  return state.interaction.payload.presentation ?? null;
}
