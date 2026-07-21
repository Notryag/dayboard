"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { apiFetch } from "@/lib/api/client";
import type { AgentRun, AgentRunStatus } from "@/lib/api/types";
import type { ChatMessage } from "./ChatMessageList";
import {
  initialMessages,
  type ConversationMessage,
  upsertAssistantMessage,
} from "./conversationMessages";
import { isTerminalRunEvent, parseRunEvent, runEventNames, type RunEvent } from "./runEvents";
import type { RunActivityStep } from "./RunActivityTicker";

type RunStreamState = {
  messages: ChatMessage[];
  progress: RunActivityStep[];
  scheduleRevision: number;
};

type RunStreamAction =
  | { type: "messages_replaced"; messages: ChatMessage[] }
  | { type: "message_appended"; message: ChatMessage }
  | { type: "progress_reset" }
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
      return { ...state, progress: [...state.progress, event.step] };
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
          parts: message.parts?.some(
            (candidate) => candidate.tool_call_id === event.part.tool_call_id,
          ) ? message.parts : [...(message.parts ?? []), event.part],
        })),
        scheduleRevision: state.scheduleRevision + 1,
      };
    case "completed":
    case "failed":
    case "cancelled":
    case "clarification":
      return event.parts ? {
        ...state,
        messages: upsertAssistantMessage(state.messages, runId, (message) => ({
          ...message,
          parts: event.parts,
        })),
      } : state;
    case "replay_gap":
      return state;
  }
}

function runStreamReducer(state: RunStreamState, action: RunStreamAction): RunStreamState {
  switch (action.type) {
    case "messages_replaced":
      return { ...state, messages: action.messages };
    case "message_appended":
      return { ...state, messages: [...state.messages, action.message] };
    case "progress_reset":
      return { ...state, progress: [] };
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
          parts: action.message.message_metadata.parts ?? message.parts,
        })),
      };
  }
}

function terminalFallback(event: RunEvent) {
  if (event.type === "failed") return "请求没有成功。请稍后再试。";
  if (event.type === "cancelled") return "请求已取消。";
  return "已处理完成。";
}

export function useRunStream(apiUrl: string) {
  const [state, dispatch] = useReducer(runStreamReducer, {
    messages: initialMessages,
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
        void apiFetch(`/api/threads/${threadId}/messages`)
          .then((response) => response.json() as Promise<ConversationMessage[]>)
          .then((history) => {
            if (settled) return;
            const message = history.find(
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
            event = parseRunEvent(rawEvent.type, (rawEvent as MessageEvent<string>).data);
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
          if (isTerminalRunEvent(event)) finish(stream, event.content ?? terminalFallback(event));
        };

        for (const eventName of runEventNames) stream.addEventListener(eventName, handleEvent);

        stream.onerror = () => {
          if (settled) return;
          void apiFetch(`/api/runs/${runId}`)
            .then((response) => response.json() as Promise<AgentRun>)
            .then((run) => {
              if (terminalStatuses.has(run.status)) {
                if (!terminalReconnectAttempted) {
                  terminalReconnectAttempted = true;
                  stream.close();
                  connect();
                  return;
                }
                finish(stream, run.result_message ?? "请求已结束。");
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
  }, [apiUrl]);

  return useMemo(() => ({ state, dispatch, followRun }), [followRun, state]);
}
