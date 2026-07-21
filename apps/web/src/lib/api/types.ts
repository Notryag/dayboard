import type { components } from "./schema";

type Schemas = components["schemas"];

export type Account = Schemas["AccountResponse"];
export type AgentRun = Schemas["AgentRun"];
export type AgentRunStatus = Schemas["AgentRunStatus"];
export type AuthCapabilities = Schemas["AuthCapabilitiesResponse"];
export type CalendarEntry = Schemas["CalendarEntryView"];
export type CalendarEntryUpdate = Schemas["CalendarEntryUpdateRequest"];
export type CalendarSchedulePage = Schemas["SchedulePage_CalendarEntryView_"];
export type ClarificationChoice = Schemas["ClarificationChoiceRequest"];
export type CommandRequest = Schemas["CommandRequest"];
export type CommandRun = Schemas["CommandRunResponse"];
export type ConversationMessage = Schemas["ConversationMessage"];
export type ConversationState = Schemas["ConversationState"];
export type ConversationThread = Schemas["ConversationThread"];
export type Login = Schemas["LoginRequest"];
export type PasswordReset = Schemas["PasswordResetRequest"];
export type PasswordResetConfirm = Schemas["PasswordResetConfirmRequest"];
export type Registration = Schemas["RegisterRequest"];
export type Reminder = Schemas["Reminder"];
export type ScheduleMutation = Schemas["ScheduleMutationRequest"];
export type TaskItem = Schemas["TaskItemView"];
export type TaskItemUpdate = Schemas["TaskItemUpdateRequest"];
export type TaskSchedulePage = Schemas["SchedulePage_TaskItemView_"];
export type ThreadCreate = Schemas["ThreadCreateRequest"];
export type VoiceCapabilities = Schemas["VoiceCapabilities"];
export type VoiceTranscript = Schemas["VoiceTranscript"];
