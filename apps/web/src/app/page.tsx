"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  MessageCircle,
} from "lucide-react";
import { AuthBoundary } from "@/features/auth/AuthBoundary";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiBaseUrl, apiFetch, userFacingApiError } from "@/lib/api/client";
import {
  getConversationState,
  submitClarificationChoice,
} from "@/features/clarifications/api";
import type {
  ClarificationInteraction as Interaction,
  ConversationState,
} from "@/features/clarifications/types";
import {
  RunActivityTicker,
  type RunActivityStep,
} from "@/features/chat/RunActivityTicker";
import { ConversationBootstrapNotice } from "@/features/chat/ConversationBootstrapNotice";
import { ChatMessageList, type ChatMessage } from "@/features/chat/ChatMessageList";
import { Composer, type InputMode } from "@/features/chat/Composer";
import { SchedulePanel } from "@/features/schedule/SchedulePanel";
import { ScheduleSettingsDrawer } from "@/features/schedule/ScheduleSettingsDrawer";
import { ScheduleUndoToast } from "@/features/schedule/ScheduleUndoToast";
import type { ScheduleChange, ScheduleResultPart } from "@/features/schedule/types";
import styles from "./page.module.css";

type PrimaryView = "chat" | "schedule";

type CommandRunResponse = {
  run_id: string;
  status: "queued";
  thread_id: string;
};

type ConversationThread = { id: string };

type ConversationMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  created_at: string;
  run_id: string;
  message_metadata: {
    parts?: ScheduleResultPart[];
  };
};

type RunStreamPayload = {
  content?: string | null;
  delta?: string;
  tool_call_id?: string;
  operation?: string;
  item?: ScheduleResultPart["item"];
  parts?: ScheduleResultPart[];
};

type AgentRun = {
  id: string;
  status: "queued" | "running" | "needs_clarification" | "completed" | "failed" | "cancelled";
  result_message: string | null;
};

const terminalRunStatuses = new Set<AgentRun["status"]>([
  "needs_clarification",
  "completed",
  "failed",
  "cancelled",
]);

const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    text: "今天想安排什么？你可以直接说“明天下午三点提醒我开产品会”。",
    time: "",
  },
];

type UndoNotice = NonNullable<ScheduleChange["undo"]> & {
  id: string;
  busy: boolean;
  error: string | null;
};

function currentTimeLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function clarificationChoiceLabel(interaction: Interaction, optionKey: string) {
  if (interaction.type === "suggested_choice") {
    const option = interaction.options.find((candidate) => candidate.key === optionKey);
    return option ? `选择“${option.label}”` : null;
  }
  const option = interaction.options.find((candidate) => candidate.key === optionKey);
  if (!option) return null;
  const time = new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: option.timezone,
  }).format(new Date(option.start_time));
  return `选择“${option.title} · ${time}”`;
}

function createMessage(
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

function persistedMessage(message: ConversationMessage): ChatMessage {
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

function upsertAssistantMessage(
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

function ChatHome() {
  const { account, logout } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeProgress, setActiveProgress] = useState<RunActivityStep[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState<ConversationState | null>(null);
  const [activeView, setActiveView] = useState<PrimaryView>("chat");
  const [scheduleRevision, setScheduleRevision] = useState(0);
  const [inputMode, setInputMode] = useState<InputMode>("voice");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [isThreadBootstrapping, setIsThreadBootstrapping] = useState(true);
  const [undoNotice, setUndoNotice] = useState<UndoNotice | null>(null);
  const [chatHeaderHidden, setChatHeaderHidden] = useState(false);
  const activeStreamRef = useRef<EventSource | null>(null);
  const initializingThreadRef = useRef(false);
  const lastChatScrollTopRef = useRef(0);
  const messagesRef = useRef<HTMLElement>(null);

  const apiUrl = useMemo(apiBaseUrl, []);
  const timezone = account?.timezone ?? "Asia/Shanghai";

  useEffect(() => {
    return () => activeStreamRef.current?.close();
  }, []);

  useEffect(() => {
    if (!undoNotice || undoNotice.busy) return;
    const timeout = window.setTimeout(() => setUndoNotice(null), 6000);
    return () => window.clearTimeout(timeout);
  }, [undoNotice]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const container = messagesRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [conversationState, isSubmitting, messages]);

  useEffect(() => {
    if (initializingThreadRef.current) return;
    initializingThreadRef.current = true;
    setBootstrapError(null);
    setIsThreadBootstrapping(true);

    async function createThread(): Promise<string> {
      const response = await apiFetch("/api/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const thread = (await response.json()) as ConversationThread;
      localStorage.setItem("dayboard.thread_id", thread.id);
      return thread.id;
    }

    async function initializeThread() {
      let resolvedThreadId = localStorage.getItem("dayboard.thread_id");
      let history: ConversationMessage[] = [];
      if (resolvedThreadId) {
        try {
          const response = await apiFetch(`/api/threads/${resolvedThreadId}/messages`);
          history = (await response.json()) as ConversationMessage[];
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            localStorage.removeItem("dayboard.thread_id");
            resolvedThreadId = null;
          } else {
            throw error;
          }
        }
      }
      resolvedThreadId ??= await createThread();
      const state = await getConversationState(resolvedThreadId);
      setThreadId(resolvedThreadId);
      setConversationState(state);
      setMessages(history.length ? history.map(persistedMessage) : initialMessages);

      const activeResponse = await apiFetch(
        `/api/threads/${resolvedThreadId}/active-run`,
      );
      const activeRun = (await activeResponse.json()) as AgentRun | null;
      if (activeRun) {
        setIsSubmitting(true);
        setActiveProgress([]);
        setActiveRunId(activeRun.id);
        try {
          const result = await followRun(activeRun.id, resolvedThreadId);
          await refreshConversationState(resolvedThreadId);
          setScheduleRevision((current) => current + 1);
          setMessages((current) =>
            upsertAssistantMessage(current, activeRun.id, (message) => ({
              ...message,
              text: result,
            })),
          );
        } finally {
          setIsSubmitting(false);
          setActiveProgress([]);
          setActiveRunId(null);
        }
      }
    }

    void initializeThread()
      .catch((error: unknown) => {
        initializingThreadRef.current = false;
        setBootstrapError(userFacingApiError(error, "无法加载对话，请稍后重试。"));
      })
      .finally(() => setIsThreadBootstrapping(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapAttempt]);

  function followRun(runId: string, runThreadId: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const progress: RunActivityStep[] = [];
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

      function connect() {
        const stream = new EventSource(
          `${apiUrl}/api/runs/${runId}/events/stream`,
          { withCredentials: true },
        );
        activeStreamRef.current = stream;
        stream.onopen = () => {
          retries = 0;
        };

        function parseEvent(event: Event) {
          const messageEvent = event as MessageEvent<string>;
          return JSON.parse(messageEvent.data) as RunStreamPayload;
        }

        for (const [eventType, fallbackText] of Object.entries(progressLabels)) {
          stream.addEventListener(eventType, (event) => {
            const payload = parseEvent(event);
            const useEventContent = eventType !== "run_created" && eventType !== "run_started";
            const step = {
              eventType,
              text: useEventContent ? (payload.content ?? fallbackText) : fallbackText,
            };
            progress.push(step);
            setActiveProgress([...progress]);
          });
        }

        stream.addEventListener("assistant_text_delta", (event) => {
          const payload = parseEvent(event);
          if (!payload.delta || replayIncomplete) return;
          setMessages((current) =>
            upsertAssistantMessage(current, runId, (message) => ({
              ...message,
              text: message.text + payload.delta,
            })),
          );
        });

        stream.addEventListener("stream_replay_gap", () => {
          replayIncomplete = true;
          void apiFetch(`/api/threads/${runThreadId}/messages`)
            .then((response) => response.json() as Promise<ConversationMessage[]>)
            .then((history) => {
              const persisted = history.find(
                (message) => message.role === "assistant" && message.run_id === runId,
              );
              setMessages((current) =>
                upsertAssistantMessage(current, runId, (message) => ({
                  ...message,
                  text: persisted?.content ?? "",
                  parts: persisted?.message_metadata.parts ?? message.parts,
                })),
              );
            })
            .catch(() => undefined);
        });

        stream.addEventListener("schedule_item_result", (event) => {
          const payload = parseEvent(event);
          if (!payload.tool_call_id || !payload.operation || !payload.item) return;
          const part: ScheduleResultPart = {
            tool_call_id: payload.tool_call_id,
            operation: payload.operation,
            item: payload.item,
          };
          setMessages((current) =>
            upsertAssistantMessage(current, runId, (message) => ({
              ...message,
              parts: message.parts?.some(
                (candidate) => candidate.tool_call_id === part.tool_call_id,
              )
                ? message.parts
                : [...(message.parts ?? []), part],
            })),
          );
          setScheduleRevision((current) => current + 1);
        });

        for (const eventType of ["run_completed", "clarification_requested"] as const) {
          stream.addEventListener(eventType, (event) => {
            const payload = parseEvent(event);
            if (payload.parts) {
              setMessages((current) =>
                upsertAssistantMessage(current, runId, (message) => ({
                  ...message,
                  parts: payload.parts,
                })),
              );
            }
            finish(stream, payload.content ?? "已处理完成。");
          });
        }

        stream.addEventListener("run_failed", (event) => {
          const payload = parseEvent(event);
          if (payload.parts) {
            setMessages((current) =>
              upsertAssistantMessage(current, runId, (message) => ({
                ...message,
                parts: payload.parts,
              })),
            );
          }
          finish(stream, payload.content ?? "请求没有成功。请稍后再试。");
        });
        stream.addEventListener("run_cancelled", (event) => {
          const payload = parseEvent(event);
          if (payload.parts) {
            setMessages((current) =>
              upsertAssistantMessage(current, runId, (message) => ({
                ...message,
                parts: payload.parts,
              })),
            );
          }
          finish(stream, payload.content ?? "请求已取消。");
        });

        stream.onerror = () => {
          if (settled) return;
          void apiFetch(`/api/runs/${runId}`)
            .then((response) => response.json() as Promise<AgentRun>)
            .then((run) => {
              if (terminalRunStatuses.has(run.status)) {
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
  }

  async function refreshConversationState(resolvedThreadId: string) {
    const state = await getConversationState(resolvedThreadId);
    setConversationState(state);
  }

  async function handleSubmit(submittedText: string) {
    const text = submittedText.trim();
    if (!text || isSubmitting || !threadId) {
      return;
    }

    setInput("");
    setIsSubmitting(true);
    setActiveProgress([]);
    setMessages((current) => [...current, createMessage("user", text)]);

    try {
      const response = await apiFetch(`/api/threads/${threadId}/command-runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ message: text }),
      });

      const command: CommandRunResponse = await response.json();
      setActiveRunId(command.run_id);
      const result = await followRun(command.run_id, threadId);

      await refreshConversationState(threadId);
      setScheduleRevision((current) => current + 1);

      setMessages((current) =>
        upsertAssistantMessage(current, command.run_id, (message) => ({
          ...message,
          text: result,
        })),
      );
    } catch (error) {
      setMessages((current) => [
        ...current,
        createMessage(
          "assistant",
          userFacingApiError(error, "请求没有成功。请稍后再试。"),
        ),
      ]);
    } finally {
      setIsSubmitting(false);
      setActiveProgress([]);
      setActiveRunId(null);
    }
  }

  async function handleClarificationChoice(optionKey: string) {
    const interaction = conversationState?.state_data.interaction;
    if (!threadId || !interaction || isSubmitting) return;
    const choiceLabel = clarificationChoiceLabel(interaction, optionKey);
    if (!choiceLabel) return;

    setIsSubmitting(true);
    setActiveProgress([]);
    setMessages((current) => [
      ...current,
      createMessage("user", choiceLabel),
    ]);
    try {
      const command = await submitClarificationChoice(threadId, {
        state_version: conversationState.version,
        option_key: optionKey,
      });
      setActiveRunId(command.run_id);
      const result = await followRun(command.run_id, threadId);
      await refreshConversationState(threadId);
      setScheduleRevision((current) => current + 1);
      setMessages((current) =>
        upsertAssistantMessage(current, command.run_id, (message) => ({
          ...message,
          text: result,
        })),
      );
    } catch {
      await refreshConversationState(threadId).catch(() => undefined);
      setMessages((current) => [
        ...current,
        createMessage("assistant", "这个选项已经失效，请重新选择。"),
      ]);
    } finally {
      setIsSubmitting(false);
      setActiveProgress([]);
      setActiveRunId(null);
    }
  }

  async function handleCancel() {
    if (!activeRunId) {
      return;
    }
    try {
      await apiFetch(`/api/runs/${activeRunId}/cancel`, { method: "POST" });
    } catch (error) {
      setMessages((current) => [
        ...current,
        createMessage("assistant", userFacingApiError(error, "暂时无法停止，请稍后重试。")),
      ]);
    }
  }

  function handleScheduleChanged(change?: ScheduleChange) {
    setScheduleRevision((current) => current + 1);
    if (change?.undo) {
      setUndoNotice({
        ...change.undo,
        id: crypto.randomUUID(),
        busy: false,
        error: null,
      });
    }
  }

  async function handleUndo() {
    const notice = undoNotice;
    if (!notice || notice.busy) return;
    setUndoNotice({ ...notice, busy: true, error: null });
    try {
      await notice.run();
      setScheduleRevision((current) => current + 1);
      setUndoNotice(null);
    } catch (error) {
      setUndoNotice((current) => current?.id === notice.id
        ? {
            ...current,
            busy: false,
            error: userFacingApiError(error, "撤销失败，请刷新后重试。"),
          }
        : current);
    }
  }

  function selectView(view: PrimaryView) {
    setChatHeaderHidden(false);
    setActiveView(view);
    if (view === "schedule") setScheduleRevision((current) => current + 1);
  }

  function handleChatScroll(scrollTop: number) {
    const normalizedScrollTop = Math.max(0, scrollTop);
    const previousScrollTop = lastChatScrollTopRef.current;
    lastChatScrollTopRef.current = normalizedScrollTop;
    if (normalizedScrollTop <= 8) {
      setChatHeaderHidden(false);
    } else if (normalizedScrollTop > previousScrollTop) {
      setChatHeaderHidden(true);
    } else if (normalizedScrollTop < previousScrollTop) {
      setChatHeaderHidden(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.appShell}>
        <header
          className={`${styles.appHeader} ${
            activeView === "chat" && chatHeaderHidden ? styles.appHeaderHidden : ""
          }`}
        >
          <div className={styles.headerLeading}>
            <button
              aria-label={activeView === "chat" ? "打开日程" : "返回对话"}
              className={styles.floatingHeaderButton}
              onClick={() => selectView(activeView === "chat" ? "schedule" : "chat")}
              title={activeView === "chat" ? "日程" : "对话"}
              type="button"
            >
              {activeView === "chat" ? (
                <CalendarDays aria-hidden="true" size={19} />
              ) : (
                <MessageCircle aria-hidden="true" size={19} />
              )}
            </button>
          </div>
          <h1 className={styles.brand}>Dayboard</h1>
          <div className={styles.headerTrailing}>
            <ScheduleSettingsDrawer
              accountName={account?.display_name || account?.username || "Dayboard 用户"}
              onLogout={() => void logout()}
              timezone={timezone}
            />
          </div>
        </header>

        <div className={styles.workspace}>
          <section
            aria-label="对话"
            className={`${styles.chatPane} ${
              activeView === "chat" ? styles.paneActive : ""
            }`}
            id="chat-panel"
            role="region"
          >
            <ChatMessageList
              conversationState={conversationState}
              isSubmitting={isSubmitting}
              messages={messages}
              onChanged={handleScheduleChanged}
              onClarificationChoice={(optionKey) => void handleClarificationChoice(optionKey)}
              onScrollPositionChange={handleChatScroll}
              scrollRef={messagesRef}
              timezone={timezone}
            />

            <div className={styles.composerDock}>
              {bootstrapError ? (
                <ConversationBootstrapNotice
                  busy={isThreadBootstrapping}
                  error={bootstrapError}
                  onRetry={() => setBootstrapAttempt((current) => current + 1)}
                />
              ) : null}
              {isSubmitting ? (
                <RunActivityTicker
                  steps={
                    activeProgress.length
                      ? activeProgress
                      : [{ eventType: "submitting", text: "正在提交请求" }]
                  }
                />
              ) : null}
              <Composer
                activeRunId={activeRunId}
                disabled={!threadId || isThreadBootstrapping}
                inputMode={inputMode}
                isSubmitting={isSubmitting}
                onCancelRun={() => void handleCancel()}
                onChange={setInput}
                onInputModeChange={setInputMode}
                onSubmit={(text) => void handleSubmit(text)}
                value={input}
              />
            </div>
          </section>

          <div
            aria-label="日程"
            className={`${styles.schedulePane} ${
              activeView === "schedule" ? styles.paneActive : ""
            }`}
            id="schedule-panel"
            role="region"
          >
            <SchedulePanel
              active={activeView === "schedule"}
              onChanged={handleScheduleChanged}
              refreshKey={scheduleRevision}
              timezone={timezone}
            />
          </div>
        </div>

        {undoNotice ? (
          <ScheduleUndoToast
            busy={undoNotice.busy}
            error={undoNotice.error}
            label={undoNotice.label}
            onUndo={() => void handleUndo()}
          />
        ) : null}
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <AuthBoundary>
      <ChatHome />
    </AuthBoundary>
  );
}
