"use client";

import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  CalendarRange,
  LogOut,
  MessageCircle,
  Sparkles,
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
import { ChatMessageList, type ChatMessage } from "@/features/chat/ChatMessageList";
import { Composer } from "@/features/chat/Composer";
import { SchedulePanel } from "@/features/schedule/SchedulePanel";
import { dateKeyInTimezone, formatAccessibleDate } from "@/features/schedule/date";
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
};

type RunEvent = {
  seq: number;
  event_type: string;
  content: string | null;
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
    time: "09:20",
  },
];

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
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: currentTimeLabel(),
    runId,
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
  };
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
  const activeStreamRef = useRef<EventSource | null>(null);
  const initializingThreadRef = useRef(false);
  const messagesRef = useRef<HTMLElement>(null);

  const apiUrl = useMemo(apiBaseUrl, []);
  const timezone = account?.timezone ?? "Asia/Shanghai";
  const todayLabel = useMemo(
    () => formatAccessibleDate(dateKeyInTimezone(new Date(), timezone)),
    [timezone],
  );

  useEffect(() => {
    return () => activeStreamRef.current?.close();
  }, []);

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
          const result = await followRun(activeRun.id);
          await refreshConversationState(resolvedThreadId);
          setScheduleRevision((current) => current + 1);
          setMessages((current) =>
            current.some(
              (message) => message.role === "assistant" && message.runId === activeRun.id,
            )
              ? current
              : [...current, createMessage("assistant", result, activeRun.id)],
          );
        } finally {
          setIsSubmitting(false);
          setActiveProgress([]);
          setActiveRunId(null);
        }
      }
    }

    void initializeThread().catch((error: unknown) => {
      initializingThreadRef.current = false;
      setMessages([
        createMessage("assistant", userFacingApiError(error, "无法加载对话，请稍后重试。")),
      ]);
    });
    // Session thread bootstrap must run once per authenticated mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function followRun(runId: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const progress: RunActivityStep[] = [];
      let cursor = 0;
      let retries = 0;
      let settled = false;

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
        calendar_entry_created: "日程已创建",
        task_creation_started: "正在创建任务",
        task_item_created: "任务已创建",
      };

      function connect() {
        const stream = new EventSource(
          `${apiUrl}/api/runs/${runId}/events/stream?after_seq=${cursor}`,
          { withCredentials: true },
        );
        activeStreamRef.current = stream;

        function parseEvent(event: Event) {
          const runEvent = JSON.parse((event as MessageEvent<string>).data) as RunEvent;
          cursor = Math.max(cursor, runEvent.seq);
          return runEvent;
        }

        for (const [eventType, fallbackText] of Object.entries(progressLabels)) {
          stream.addEventListener(eventType, (event) => {
            const runEvent = parseEvent(event);
            const useEventContent = eventType !== "run_created" && eventType !== "run_started";
            const step = {
              eventType,
              text: useEventContent ? (runEvent.content ?? fallbackText) : fallbackText,
            };
            progress.push(step);
            setActiveProgress([...progress]);
          });
        }

        for (const eventType of ["run_completed", "clarification_requested"] as const) {
          stream.addEventListener(eventType, (event) => {
            const runEvent = parseEvent(event);
            finish(stream, runEvent.content ?? "已处理完成。");
          });
        }

        stream.addEventListener("run_failed", (event) => {
          const runEvent = parseEvent(event);
          finish(stream, runEvent.content ?? "请求没有成功。请稍后再试。");
        });
        stream.addEventListener("run_cancelled", (event) => {
          const runEvent = parseEvent(event);
          finish(stream, runEvent.content ?? "请求已取消。");
        });

        stream.onerror = () => {
          stream.close();
          if (settled) return;
          activeStreamRef.current = null;
          void apiFetch(`/api/runs/${runId}`)
            .then((response) => response.json() as Promise<AgentRun>)
            .then((run) => {
              if (terminalRunStatuses.has(run.status)) {
                finish(stream, run.result_message ?? "请求已结束。");
                return;
              }
              retries += 1;
              if (retries > 4) {
                settled = true;
                reject(new Error("Run event stream disconnected"));
                return;
              }
              window.setTimeout(connect, Math.min(500 * 2 ** retries, 4000));
            })
            .catch((error: unknown) => {
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
      const result = await followRun(command.run_id);

      await refreshConversationState(threadId);
      setScheduleRevision((current) => current + 1);

      setMessages((current) => [
        ...current,
        createMessage("assistant", result, command.run_id),
      ]);
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
      const result = await followRun(command.run_id);
      await refreshConversationState(threadId);
      setScheduleRevision((current) => current + 1);
      setMessages((current) => [
        ...current,
        createMessage("assistant", result, command.run_id),
      ]);
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
    await apiFetch(`/api/runs/${activeRunId}/cancel`, { method: "POST" });
  }

  function selectView(view: PrimaryView) {
    setActiveView(view);
    if (view === "schedule") setScheduleRevision((current) => current + 1);
  }

  function handleViewTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextView: PrimaryView =
      event.key === "ArrowLeft" || event.key === "Home" ? "chat" : "schedule";
    selectView(nextView);
    window.requestAnimationFrame(() => document.getElementById(`${nextView}-tab`)?.focus());
  }

  return (
    <div className={styles.page}>
      <main className={styles.appShell}>
        <header className={styles.appHeader}>
          <div className={styles.brand}>
            <span aria-hidden="true" className={styles.brandMark}>
              <CalendarRange size={21} strokeWidth={2.2} />
            </span>
            <div className={styles.brandText}>
              <h1>Dayboard</h1>
              <p className={styles.brandDate}>{todayLabel}</p>
            </div>
          </div>
          <div className={styles.headerActions}>
            <span className={styles.accountName}>
              {account?.display_name || account?.username}
            </span>
            <button
              className={styles.headerButton}
              onClick={() => void logout()}
              type="button"
              aria-label="退出登录"
              title="退出登录"
            >
              <LogOut size={18} />
            </button>
          </div>
        </header>

        <nav
          aria-label="主要视图"
          aria-orientation="horizontal"
          className={styles.viewTabs}
          role="tablist"
        >
          <button
            aria-controls="chat-panel"
            aria-selected={activeView === "chat"}
            className={styles.viewTab}
            id="chat-tab"
            onClick={() => selectView("chat")}
            onKeyDown={handleViewTabKeyDown}
            role="tab"
            tabIndex={activeView === "chat" ? 0 : -1}
            type="button"
          >
            <MessageCircle aria-hidden="true" size={17} />
            对话
          </button>
          <button
            aria-controls="schedule-panel"
            aria-selected={activeView === "schedule"}
            className={styles.viewTab}
            id="schedule-tab"
            onClick={() => selectView("schedule")}
            onKeyDown={handleViewTabKeyDown}
            role="tab"
            tabIndex={activeView === "schedule" ? 0 : -1}
            type="button"
          >
            <CalendarDays aria-hidden="true" size={17} />
            日程
          </button>
        </nav>

        <div className={styles.workspace}>
          <section
            aria-labelledby="chat-tab"
            className={`${styles.chatPane} ${
              activeView === "chat" ? styles.paneActive : ""
            }`}
            id="chat-panel"
            role="tabpanel"
          >
            <header className={styles.paneHeader}>
              <div className={styles.paneTitle}>
                <MessageCircle aria-hidden="true" size={18} />
                <h2>对话</h2>
              </div>
              <span
                aria-label="AI 可用"
                className={styles.aiSignal}
                role="img"
                title="AI 可用"
              >
                <Sparkles size={17} strokeWidth={2.2} />
              </span>
            </header>

            <ChatMessageList
              conversationState={conversationState}
              isSubmitting={isSubmitting}
              messages={messages}
              onClarificationChoice={(optionKey) => void handleClarificationChoice(optionKey)}
              scrollRef={messagesRef}
            />

            <div className={styles.composerDock}>
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
                disabled={!threadId}
                isSubmitting={isSubmitting}
                onCancelRun={() => void handleCancel()}
                onChange={setInput}
                onSubmit={(text) => void handleSubmit(text)}
                value={input}
              />
            </div>
          </section>

          <div
            aria-labelledby="schedule-tab"
            className={`${styles.schedulePane} ${
              activeView === "schedule" ? styles.paneActive : ""
            }`}
            id="schedule-panel"
            role="tabpanel"
          >
            <SchedulePanel
              active={activeView === "schedule"}
              refreshKey={scheduleRevision}
              timezone={timezone}
            />
          </div>
        </div>
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
