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

export type ConversationState = {
  thread_id: string;
  pending_action: string | null;
  pending_question: string | null;
  state_data: {
    source_run_id?: string;
    interaction?: CalendarEntryChoiceInteraction;
  };
  version: number;
  expires_at: string | null;
};

export type ClarificationChoiceResponse = {
  state_version: number;
  option_key: string;
};
