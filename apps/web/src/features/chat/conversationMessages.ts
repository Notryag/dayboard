import type { ChatMessage } from "./ChatMessageList";
import type { ScheduleResultPart } from "@/features/schedule/types";
import type { ConversationMessage as ApiConversationMessage } from "@/lib/api/types";

export type ConversationMessage = Omit<ApiConversationMessage, "message_metadata"> & {
  message_metadata: { parts?: ScheduleResultPart[] };
};

export const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    text: "今天想安排什么？你可以直接说“明天下午三点提醒我开产品会”。",
    time: "",
  },
];

function currentTimeLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
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
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: currentTimeLabel(),
    runId,
    parts,
  };
}

export function persistedMessage(message: ConversationMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    time: new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(message.created_at)),
    runId: message.run_id,
    parts: message.message_metadata.parts ?? [],
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
