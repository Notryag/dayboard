import type { ScheduleDisplayItem, ScheduleResultPart } from "@/features/schedule/types";
import type { RunActivityStep } from "./RunActivityTicker";

const progressLabels = {
  run_created: "请求已进入队列",
  run_started: "正在处理",
  tool_call_started: "正在执行操作",
  tool_call_completed: "操作完成",
  tool_call_error: "操作失败",
  conflict_check_started: "正在检查日程冲突",
  conflict_check_completed: "日程冲突检查完成",
} as const;

const scheduleOperations = new Set<ScheduleResultPart["operation"]>([
  "calendar_entry_created",
  "calendar_entry_found",
  "calendar_entry_rescheduled",
  "calendar_entry_cancelled",
  "task_item_created",
  "task_item_found",
  "task_item_updated",
]);

function isScheduleOperation(value: unknown): value is ScheduleResultPart["operation"] {
  return typeof value === "string"
    && scheduleOperations.has(value as ScheduleResultPart["operation"]);
}

type TerminalEvent =
  | { type: "completed"; content: string | null; parts?: ScheduleResultPart[] }
  | { type: "failed"; content: string | null; parts?: ScheduleResultPart[] }
  | { type: "cancelled"; content: string | null; parts?: ScheduleResultPart[] }
  | { type: "clarification"; content: string | null; parts?: ScheduleResultPart[] };

export type RunEvent =
  | { type: "assistant_delta"; delta: string }
  | { type: "schedule_result"; part: ScheduleResultPart }
  | { type: "schedule_results"; parts: ScheduleResultPart[] }
  | { type: "progress"; step: RunActivityStep }
  | { type: "replay_gap" }
  | TerminalEvent;

export const runEventNames = [
  ...Object.keys(progressLabels),
  "assistant_text_delta",
  "stream_replay_gap",
  "schedule_item_result",
  "schedule_items_result",
  "run_completed",
  "clarification_requested",
  "run_failed",
  "run_cancelled",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function scheduleItem(value: unknown): ScheduleDisplayItem | null {
  if (!isRecord(value) || (value.kind !== "calendar" && value.kind !== "task")) return null;
  if (!isRecord(value.value) || typeof value.value.id !== "string") return null;
  return value as ScheduleDisplayItem;
}

function schedulePart(value: unknown): ScheduleResultPart | null {
  if (!isRecord(value)) return null;
  const item = scheduleItem(value.item);
  if (
    typeof value.tool_call_id !== "string"
    || !isScheduleOperation(value.operation)
    || !item
  ) {
    return null;
  }
  const operationMatchesItem = item.kind === "calendar"
    ? value.operation.startsWith("calendar_entry_")
    : value.operation.startsWith("task_item_");
  if (!operationMatchesItem) return null;
  return {
    tool_call_id: value.tool_call_id,
    operation: value.operation,
    item,
  };
}

export function parseScheduleResultParts(value: unknown): ScheduleResultPart[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((candidate) => {
    const part = schedulePart(candidate);
    return part ? [part] : [];
  });
}

function terminalParts(payload: Record<string, unknown>): ScheduleResultPart[] | undefined {
  if (payload.parts === undefined) return undefined;
  if (!Array.isArray(payload.parts)) throw new Error("Run terminal parts must be an array");
  const parts = payload.parts.map(schedulePart);
  if (parts.some((part) => part === null)) throw new Error("Invalid schedule result in Run event");
  return parts as ScheduleResultPart[];
}

export function parseRunEvent(eventName: string, rawData: string): RunEvent {
  let value: unknown;
  try {
    value = JSON.parse(rawData);
  } catch {
    throw new Error(`Invalid JSON for Run event: ${eventName}`);
  }
  if (!isRecord(value)) throw new Error(`Invalid payload for Run event: ${eventName}`);

  if (eventName in progressLabels) {
    const fallback = progressLabels[eventName as keyof typeof progressLabels];
    const useContent = eventName !== "run_created" && eventName !== "run_started";
    return {
      type: "progress",
      step: {
        eventType: eventName,
        text: useContent && typeof value.content === "string" ? value.content : fallback,
      },
    };
  }
  if (eventName === "assistant_text_delta" && typeof value.delta === "string") {
    return { type: "assistant_delta", delta: value.delta };
  }
  if (eventName === "schedule_item_result") {
    const part = schedulePart(value);
    if (part) return { type: "schedule_result", part };
  }
  if (eventName === "schedule_items_result") {
    if (!Array.isArray(value.parts)) throw new Error("Schedule results must be an array");
    const parts = value.parts.map(schedulePart);
    if (parts.some((part) => part === null)) throw new Error("Invalid schedule search result");
    return { type: "schedule_results", parts: parts as ScheduleResultPart[] };
  }
  if (eventName === "stream_replay_gap") return { type: "replay_gap" };

  const terminalType = {
    run_completed: "completed",
    clarification_requested: "clarification",
    run_failed: "failed",
    run_cancelled: "cancelled",
  }[eventName] as TerminalEvent["type"] | undefined;
  if (terminalType) {
    return {
      type: terminalType,
      content: typeof value.content === "string" ? value.content : null,
      parts: terminalParts(value),
    } as TerminalEvent;
  }
  throw new Error(`Invalid payload for Run event: ${eventName}`);
}

export function isTerminalRunEvent(event: RunEvent): event is TerminalEvent {
  return ["completed", "failed", "cancelled", "clarification"].includes(event.type);
}
