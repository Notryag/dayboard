export type CalendarEntryChoiceOption = {
  key: string;
  title: string;
  timing_kind?: "timed" | "anytime";
  scheduled_date?: string;
  start_time?: string;
  end_time?: string;
  timezone?: string;
};

export type CalendarEntryChoiceInteraction = {
  type: "calendar_entry_choice";
  options: CalendarEntryChoiceOption[];
};

export type SuggestedChoiceOption = {
  key: string;
  label: string;
};

export type SuggestedChoiceInteraction = {
  type: "suggested_choice";
  options: SuggestedChoiceOption[];
};

export type ClarificationInteraction =
  | CalendarEntryChoiceInteraction
  | SuggestedChoiceInteraction;

export type ConversationState = Omit<ApiConversationState, "state_data"> & {
  state_data: {
    source_run_id?: string;
    interaction?: ClarificationInteraction;
  };
};

export type ClarificationChoiceResponse = ClarificationChoice;
import type {
  ClarificationChoice,
  ConversationState as ApiConversationState,
} from "@/lib/api/types";
