import type {
  ClarificationChoiceResponse,
  ConversationState,
} from "./types";
import { apiFetch } from "@/lib/api/client";
import type { CommandRun } from "@/lib/api/types";

export type QueuedCommandRun = CommandRun;

export async function getConversationState(
  threadId: string,
): Promise<ConversationState | null> {
  const response = await apiFetch(`/api/threads/${threadId}/state`);
  return (await response.json()) as ConversationState | null;
}

export async function submitClarificationChoice(
  threadId: string,
  body: ClarificationChoiceResponse,
): Promise<QueuedCommandRun> {
  const response = await apiFetch(
    `/api/threads/${threadId}/clarification-responses`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(body),
    },
  );
  return (await response.json()) as QueuedCommandRun;
}
