"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type { ChatMessage } from "./ChatMessageList";
import type { RunActivityStep } from "./RunActivityTicker";
import {
  initialMessages,
  type ConversationMessage,
  upsertAssistantMessage,
} from "./conversationMessages";
import type { ScheduleResultPart } from "@/features/schedule/types";
import { apiFetch } from "@/lib/api/client";
import type { AgentRun, AgentRunStatus } from "@/lib/api/types";

type RunStreamPayload = {
  content?: string | null;
  delta?: string;
  tool_call_id?: string;
  operation?: string;
  item?: ScheduleResultPart["item"];
  parts?: ScheduleResultPart[];
};

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
  | { type: "stream_event"; eventType: string; payload: RunStreamPayload; runId: string }
  | { type: "stream_replayed"; runId: string; message: ConversationMessage };

const progressLabels: Record<string, string> = {
  run_created: "请求已进入队列",
  run_started: "任务开始处理",
  agent_model_started: "正在理解你的安排",
  agent_model_completed: "已完成分析，正在执行下一步",
  tool_call_started: "正在执行操作",
  tool_call_completed: "操作完成",
  tool_call_error: "操作失败",
  conflict_check_started: "正在检查日程冲突",
  conflict_check_completed: "日程冲突检查完成",
};

const terminalStatuses = new Set<AgentRunStatus>([
  "needs_clarification",
  "completed",
  "failed",
  "cancelled",
]);

const terminalEvents = new Set([
  "run_completed",
  "clarification_requested",
  "run_failed",
  "run_cancelled",
]);

const streamEventTypes = [
  ...Object.keys(progressLabels),
  "assistant_text_delta",
  "stream_replay_gap",
  "schedule_item_result",
  ...terminalEvents,
];

function reduceStreamEvent(
  state: RunStreamState,
  action: Extract<RunStreamAction, { type: "stream_event" }>,
): RunStreamState {
  const { eventType, payload, runId } = action;
  if (eventType in progressLabels) {
    const useContent = eventType !== "run_created" && eventType !== "run_started";
    return {
      ...state,
      progress: [...state.progress, {
        eventType,
        text: useContent ? (payload.content ?? progressLabels[eventType]) : progressLabels[eventType],
      }],
    };
  }
  if (eventType === "assistant_text_delta" && payload.delta) {
    return {
      ...state,
      messages: upsertAssistantMessage(state.messages, runId, (message) => ({
        ...message,
        text: message.text + payload.delta,
      })),
    };
  }
  if (eventType === "schedule_item_result" && payload.tool_call_id && payload.operation && payload.item) {
    const part: ScheduleResultPart = {
      tool_call_id: payload.tool_call_id,
      operation: payload.operation,
      item: payload.item,
    };
    return {
      ...state,
      messages: upsertAssistantMessage(state.messages, runId, (message) => ({
        ...message,
        parts: message.parts?.some((candidate) => candidate.tool_call_id === part.tool_call_id)
          ? message.parts
          : [...(message.parts ?? []), part],
      })),
      scheduleRevision: state.scheduleRevision + 1,
    };
  }
  if (terminalEvents.has(eventType) && payload.parts) {
    return {
      ...state,
      messages: upsertAssistantMessage(state.messages, runId, (message) => ({
        ...message,
        parts: payload.parts,
      })),
    };
  }
  return state;
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
    case "stream_event":
      return reduceStreamEvent(state, action);
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

      function connect() {
        const stream = new EventSource(`${apiUrl}/api/runs/${runId}/events/stream`, {
          withCredentials: true,
        });
        activeStreamRef.current = stream;
        stream.onopen = () => { retries = 0; };

        const handleEvent = (event: Event) => {
          const eventType = event.type;
          if (eventType === "stream_replay_gap") {
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
            return;
          }
          let payload: RunStreamPayload;
          try {
            payload = JSON.parse((event as MessageEvent<string>).data) as RunStreamPayload;
          } catch {
            stream.close();
            activeStreamRef.current = null;
            settled = true;
            reject(new Error(`Invalid payload for Run event: ${eventType}`));
            return;
          }
          if (eventType !== "assistant_text_delta" || !replayIncomplete) {
            dispatch({ type: "stream_event", eventType, payload, runId });
          }
          if (terminalEvents.has(eventType)) {
            const fallback = eventType === "run_failed"
              ? "请求没有成功。请稍后再试。"
              : eventType === "run_cancelled" ? "请求已取消。" : "已处理完成。";
            finish(stream, payload.content ?? fallback);
          }
        };

        for (const eventType of streamEventTypes) {
          stream.addEventListener(eventType, handleEvent);
        }

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
              if (retries > 4) {
                stream.close();
                activeStreamRef.current = null;
                settled = true;
                reject(new Error("Run event stream disconnected"));
              }
            })
            .catch((error: unknown) => {
              stream.close();
              activeStreamRef.current = null;
              settled = true;
              reject(error);
            });
        };
      }

      connect();
    });
  }, [apiUrl]);

  return useMemo(() => ({ state, dispatch, followRun }), [followRun, state]);
}
