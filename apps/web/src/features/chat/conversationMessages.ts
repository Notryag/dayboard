import type { ChatMessage } from "./ChatMessageList";
import type { ScheduleResultPart } from "@/features/schedule/types";
import type { ConversationMessage as ApiConversationMessage } from "@/lib/api/types";
import { parseScheduleResultParts } from "./runEvents";
import { getMessage, type Locale } from "@/i18n";

export type ConversationMessage = ApiConversationMessage;

export function initialMessages(locale: Locale = "zh-CN"): ChatMessage[] {
  return [{
    id: "welcome",
    role: "assistant",
    text: getMessage(locale, "chat.greeting"),
    time: "",
  }];
}

function currentTimeLabel(locale: Locale = "zh-CN") {
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

export function createMessage(
  role: ChatMessage["role"],
  text: string,
  runId?: string,
  parts?: ScheduleResultPart[],
  locale: Locale = "zh-CN",
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: currentTimeLabel(locale),
    runId,
    parts,
  };
}

export function persistedMessage(message: ConversationMessage, locale: Locale = "zh-CN"): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    time: new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(message.created_at)),
    runId: message.run_id,
    parts: parseScheduleResultParts(message.presentation?.payload.parts),
  };
}

export function upsertAssistantMessage(
  messages: ChatMessage[],
  runId: string,
  update: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  const index = messages.findIndex(
    (message) => message.role === "assistant" && message.runId === runId,
  );
  if (index === -1) {
    return [...messages, update(createMessage("assistant", "", runId, []))];
  }
  const next = [...messages];
  next[index] = update(next[index]);
  return next;
}
