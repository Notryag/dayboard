export type CalendarEntryChoiceOption = {
  key: string;
  title: string;
  start_time: string;
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

export type ConversationState = {
  thread_id: string;
  pending_action: string | null;
  pending_question: string | null;
  state_data: {
    source_run_id?: string;
    interaction?: ClarificationInteraction;
  };
  version: number;
  expires_at: string | null;
};

export type ClarificationChoiceResponse = {
  state_version: number;
  option_key: string;
};
