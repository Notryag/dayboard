import type {
  ClarificationChoiceResponse,
  ConversationState,
} from "./types";

export type QueuedCommandRun = {
  run_id: string;
  status: "queued";
  thread_id: string;
};

export async function getConversationState(
  apiBaseUrl: string,
  threadId: string,
): Promise<ConversationState | null> {
  const response = await fetch(`${apiBaseUrl}/api/threads/${threadId}/state`);
  if (!response.ok) {
    throw new Error(`Conversation state request failed with ${response.status}`);
  }
  return (await response.json()) as ConversationState | null;
}

export async function submitClarificationChoice(
  apiBaseUrl: string,
  threadId: string,
  body: ClarificationChoiceResponse,
): Promise<QueuedCommandRun> {
  const response = await fetch(
    `${apiBaseUrl}/api/threads/${threadId}/clarification-responses`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    throw new Error(`Clarification response failed with ${response.status}`);
  }
  return (await response.json()) as QueuedCommandRun;
}
