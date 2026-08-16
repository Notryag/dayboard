"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { getMessage, useI18n } from "@/i18n";
import type { ScheduleResultPart } from "@/features/schedule/types";
import type { AgentRunStatus } from "@/lib/api/types";
import type { ChatMessage } from "./ChatMessageList";
import { getRun, getThreadMessages } from "./api";
import {
  initialMessages,
  type ConversationMessage,
  upsertAssistantMessage,
} from "./conversationMessages";
import {
  isTerminalRunEvent,
  parseRunEvent,
  parseScheduleResultParts,
  runEventNames,
  type RunEvent,
} from "./runEvents";
import {
  type RunActivityState,
  type RunActivityStep,
  settleRunActivitySteps,
  upsertRunActivityStep,
} from "./runActivity";

type RunStreamState = {
  activityRunId: string | null;
  activityState: RunActivityState;
  messages: ChatMessage[];
  progress: RunActivityStep[];
  scheduleRevision: number;
};

type RunStreamAction =
  | { type: "messages_replaced"; messages: ChatMessage[] }
  | { type: "messages_prepended"; messages: ChatMessage[] }
  | { type: "message_appended"; message: ChatMessage }
  | { type: "progress_reset" }
  | { type: "activity_failed" }
  | { type: "run_result_received"; runId: string; text: string }
  | { type: "schedule_changed" }
  | { type: "run_event"; event: RunEvent; runId: string }
  | { type: "stream_replayed"; runId: string; message: ConversationMessage };

const terminalStatuses = new Set<AgentRunStatus>([
  "needs_clarification",
  "completed",
  "failed",
  "cancelled",
]);

function reduceRunEvent(
  state: RunStreamState,
  action: Extract<RunStreamAction, { type: "run_event" }>,
): RunStreamState {
  const { event, runId } = action;
  switch (event.type) {
    case "progress":
      return {
        ...state,
        activityRunId: runId,
        activityState: "running",
        progress: upsertRunActivityStep(state.progress, event.step),
      };
    case "assistant_delta":
      return {
        ...state,
        messages: upsertAssistantMessage(state.messages, runId, (message) => ({
          ...message,
          text: message.text + event.delta,
        })),
      };
    case "schedule_result":
      return {
        ...state,
        messages: upsertAssistantMessage(state.messages, runId, (message) => ({
          ...message,
          parts: mergeScheduleParts(message.parts ?? [], [event.part]),
        })),
        scheduleRevision: state.scheduleRevision + 1,
      };
    case "schedule_results":
      return {
        ...state,
        messages: upsertAssistantMessage(state.messages, runId, (message) => ({
          ...message,
          parts: mergeScheduleParts(message.parts ?? [], event.parts),
        })),
      };
    case "completed":
    case "failed":
    case "cancelled":
    case "clarification": {
      const activityState = event.type === "failed" ? "failed"
        : event.type === "cancelled" ? "cancelled"
          : "completed";
      return {
        ...state,
        activityRunId: runId,
        activityState,
        progress: settleRunActivitySteps(state.progress, activityState),
        ...(event.parts
          ? {
              messages: upsertAssistantMessage(state.messages, runId, (message) => ({
                ...message,
                parts: event.parts,
              })),
            }
          : {}),
      };
    }
    case "replay_gap":
      return state;
  }
}

function mergeScheduleParts(
  current: ScheduleResultPart[],
  incoming: ScheduleResultPart[],
): ScheduleResultPart[] {
  const merged = [...current];
  for (const part of incoming) {
    const index = merged.findIndex(
      (candidate) => candidate.item.kind === part.item.kind
        && candidate.item.value.id === part.item.value.id,
    );
    if (index === -1) merged.push(part);
    else merged[index] = part;
  }
  return merged;
}

function runStreamReducer(state: RunStreamState, action: RunStreamAction): RunStreamState {
  switch (action.type) {
    case "messages_replaced":
      return { ...state, messages: action.messages };
    case "messages_prepended": {
      const existing = new Set(state.messages.map((message) => message.id));
      return {
        ...state,
        messages: [
          ...action.messages.filter((message) => !existing.has(message.id)),
          ...state.messages,
        ],
      };
    }
    case "message_appended":
      return { ...state, messages: [...state.messages, action.message] };
    case "progress_reset":
      return { ...state, activityRunId: null, activityState: "idle", progress: [] };
    case "activity_failed":
      return {
        ...state,
        activityState: "failed",
        progress: settleRunActivitySteps(state.progress, "failed"),
      };
    case "run_result_received":
      return {
        ...state,
        messages: upsertAssistantMessage(state.messages, action.runId, (message) => ({
          ...message,
          text: action.text,
        })),
      };
    case "schedule_changed":
      return { ...state, scheduleRevision: state.scheduleRevision + 1 };
    case "run_event":
      return reduceRunEvent(state, action);
    case "stream_replayed":
      return {
        ...state,
        messages: upsertAssistantMessage(state.messages, action.runId, (message) => ({
          ...message,
          text: action.message.content,
          parts: action.message.presentation === null
            ? message.parts
            : parseScheduleResultParts(action.message.presentation.payload.parts),
        })),
      };
  }
}

function terminalFallback(event: RunEvent, locale: "zh-CN" | "en-US") {
  if (event.type === "failed") return getMessage(locale, "chat.requestFailed");
  if (event.type === "cancelled") return getMessage(locale, "chat.cancelled");
  return getMessage(locale, "chat.completed");
}

function terminalEventFromRun(
  status: AgentRunStatus,
  content: string | null | undefined,
): RunEvent | null {
  const normalizedContent = content ?? null;
  if (status === "completed") return { type: "completed", content: normalizedContent };
  if (status === "needs_clarification") {
    return { type: "clarification", content: normalizedContent };
  }
  if (status === "failed") return { type: "failed", content: normalizedContent };
  if (status === "cancelled") return { type: "cancelled", content: normalizedContent };
  return null;
}

export function useRunStream(apiUrl: string) {
  const { locale } = useI18n();
  const [state, dispatch] = useReducer(runStreamReducer, {
    activityRunId: null,
    activityState: "idle",
    messages: initialMessages(locale),
    progress: [],
    scheduleRevision: 0,
  });
  const activeStreamRef = useRef<EventSource | null>(null);

  useEffect(() => () => activeStreamRef.current?.close(), []);

  const followRun = useCallback((runId: string, threadId: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      let retries = 0;
      let settled = false;
      let terminalReconnectAttempted = false;
      let replayIncomplete = false;

      function finish(stream: EventSource, text: string) {
        if (settled) return;
        settled = true;
        stream.close();
        activeStreamRef.current = null;
        resolve(text);
      }

      function fail(stream: EventSource, error: unknown) {
        stream.close();
        activeStreamRef.current = null;
        settled = true;
        reject(error);
      }

      function recoverConversation() {
        replayIncomplete = true;
        void getThreadMessages(threadId)
          .then((history) => {
            if (settled) return;
            const message = history.items.find(
              (candidate) => candidate.role === "assistant" && candidate.run_id === runId,
            );
            if (message) dispatch({ type: "stream_replayed", runId, message });
          })
          .catch(() => undefined);
      }

      function connect() {
        const stream = new EventSource(`${apiUrl}/api/runs/${runId}/events/stream`, {
          withCredentials: true,
        });
        activeStreamRef.current = stream;
        stream.onopen = () => { retries = 0; };

        const handleEvent = (rawEvent: Event) => {
          let event: RunEvent;
          try {
            event = parseRunEvent(rawEvent.type, (rawEvent as MessageEvent<string>).data, locale);
          } catch (error) {
            fail(stream, error);
            return;
          }
          if (event.type === "replay_gap") {
            recoverConversation();
            return;
          }
          if (event.type !== "assistant_delta" || !replayIncomplete) {
            dispatch({ type: "run_event", event, runId });
          }
          if (isTerminalRunEvent(event)) finish(stream, event.content ?? terminalFallback(event, locale));
        };

        for (const eventName of runEventNames) stream.addEventListener(eventName, handleEvent);

        stream.onerror = () => {
          if (settled) return;
          void getRun(runId)
            .then((run) => {
              if (terminalStatuses.has(run.status)) {
                if (!terminalReconnectAttempted) {
                  terminalReconnectAttempted = true;
                  stream.close();
                  connect();
                  return;
                }
                const terminalEvent = terminalEventFromRun(run.status, run.last_ai_message);
                if (terminalEvent === null) return;
                dispatch({
                  type: "run_event",
                  runId,
                  event: terminalEvent,
                });
                finish(stream, run.last_ai_message ?? getMessage(locale, "chat.ended"));
                return;
              }
              retries += 1;
              if (retries > 4) fail(stream, new Error("Run event stream disconnected"));
            })
            .catch((error: unknown) => fail(stream, error));
        };
      }

      connect();
    });
  }, [apiUrl, dispatch, locale]);

  return useMemo(() => ({ state, dispatch, followRun }), [followRun, state]);
}
