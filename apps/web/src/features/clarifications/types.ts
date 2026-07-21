import type {
  ClarificationChoice,
  ConversationState as ApiConversationState,
} from "@/lib/api/types";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseSuggestedChoice(value: unknown): SuggestedChoiceInteraction | undefined {
  if (!isRecord(value) || value.type !== "suggested_choice" || !Array.isArray(value.options)) {
    return undefined;
  }
  const options = value.options.flatMap((option) => (
    isRecord(option) && typeof option.key === "string" && typeof option.label === "string"
      ? [{ key: option.key, label: option.label }]
      : []
  ));
  return options.length === value.options.length ? { type: "suggested_choice", options } : undefined;
}

function parseCalendarEntryChoice(value: unknown): CalendarEntryChoiceInteraction | undefined {
  if (!isRecord(value) || value.type !== "calendar_entry_choice" || !Array.isArray(value.options)) {
    return undefined;
  }
  const options: CalendarEntryChoiceOption[] = [];
  for (const option of value.options) {
    if (!isRecord(option) || typeof option.key !== "string" || typeof option.title !== "string") {
      return undefined;
    }
    const timingKind = option.timing_kind === "timed" || option.timing_kind === "anytime"
      ? option.timing_kind
      : undefined;
    options.push({
      key: option.key,
      title: option.title,
      timing_kind: timingKind,
      scheduled_date: typeof option.scheduled_date === "string" ? option.scheduled_date : undefined,
      start_time: typeof option.start_time === "string" ? option.start_time : undefined,
      end_time: typeof option.end_time === "string" ? option.end_time : undefined,
      timezone: typeof option.timezone === "string" ? option.timezone : undefined,
    });
  }
  return { type: "calendar_entry_choice", options };
}

export function parseConversationState(
  state: ApiConversationState | null,
): ConversationState | null {
  if (!state) return null;
  const interaction = parseSuggestedChoice(state.state_data.interaction)
    ?? parseCalendarEntryChoice(state.state_data.interaction);
  return {
    ...state,
    state_data: {
      source_run_id: typeof state.state_data.source_run_id === "string"
        ? state.state_data.source_run_id
        : undefined,
      interaction,
    },
  };
}
