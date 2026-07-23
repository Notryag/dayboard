import { parseConversationState } from "@/features/clarifications/types";
import type { ClarificationChoiceResponse } from "@/features/clarifications/types";
import { apiClient, requireApiData } from "@/lib/api/typedClient";
import type {
  AgentRun,
  CommandRequest,
  CommandRun,
  ConversationMessagePage,
  ConversationThread,
  ThreadCreate,
} from "@/lib/api/types";

export async function createThread(body: ThreadCreate = {}): Promise<ConversationThread> {
  const { data } = await apiClient.POST("/api/threads", { body });
  return requireApiData(data);
}

export async function getPrimaryConversation(): Promise<ConversationThread> {
  const { data } = await apiClient.PUT("/api/conversation");
  return requireApiData(data);
}

export async function getThreadMessages(
  threadId: string,
  before?: string,
): Promise<ConversationMessagePage> {
  const { data } = await apiClient.GET("/api/threads/{thread_id}/messages", {
    params: {
      path: { thread_id: threadId },
      query: { before, limit: 30 },
    },
  });
  return requireApiData(data);
}

export async function getConversationState(threadId: string) {
  const { data } = await apiClient.GET("/api/threads/{thread_id}/state", {
    params: { path: { thread_id: threadId } },
  });
  return parseConversationState(requireApiData(data));
}

export async function getActiveRun(threadId: string): Promise<AgentRun | null> {
  const { data } = await apiClient.GET("/api/threads/{thread_id}/active-run", {
    params: { path: { thread_id: threadId } },
  });
  return requireApiData(data);
}

export async function getRun(runId: string): Promise<AgentRun> {
  const { data } = await apiClient.GET("/api/runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  return requireApiData(data);
}

export async function createCommandRun(
  threadId: string,
  body: CommandRequest,
): Promise<CommandRun> {
  const { data } = await apiClient.POST("/api/threads/{thread_id}/command-runs", {
    params: {
      path: { thread_id: threadId },
      header: { "Idempotency-Key": crypto.randomUUID() },
    },
    body,
  });
  return requireApiData(data);
}

export async function submitClarificationChoice(
  threadId: string,
  body: ClarificationChoiceResponse,
): Promise<CommandRun> {
  const { data } = await apiClient.POST(
    "/api/threads/{thread_id}/clarification-responses",
    {
      params: {
        path: { thread_id: threadId },
        header: { "Idempotency-Key": crypto.randomUUID() },
      },
      body,
    },
  );
  return requireApiData(data);
}

export async function cancelRun(runId: string): Promise<AgentRun> {
  const { data } = await apiClient.POST("/api/runs/{run_id}/cancel", {
    params: { path: { run_id: runId } },
  });
  return requireApiData(data);
}
