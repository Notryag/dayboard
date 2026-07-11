"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { LogOut, Mic, SendHorizontal, Square } from "lucide-react";
import { AuthBoundary } from "@/features/auth/AuthBoundary";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiBaseUrl, apiFetch, userFacingApiError } from "@/lib/api/client";
import { ClarificationInteraction } from "@/features/clarifications/ClarificationInteraction";
import {
  getConversationState,
  submitClarificationChoice,
} from "@/features/clarifications/api";
import type {
  ClarificationInteraction as Interaction,
  ConversationState,
} from "@/features/clarifications/types";
import styles from "./page.module.css";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  time: string;
  progress?: ProgressStep[];
  runId?: string;
};

type ProgressStep = {
  eventType: string;
  text: string;
};

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
  event_type: string;
  content: string | null;
};

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
  progress?: ProgressStep[],
  runId?: string,
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: currentTimeLabel(),
    progress,
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
  const { logout } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeProgress, setActiveProgress] = useState<ProgressStep[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState<ConversationState | null>(null);
  const activeStreamRef = useRef<EventSource | null>(null);
  const initializingThreadRef = useRef(false);

  const apiUrl = useMemo(apiBaseUrl, []);

  useEffect(() => {
    return () => activeStreamRef.current?.close();
  }, []);

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
    }

    void initializeThread().catch((error: unknown) => {
      initializingThreadRef.current = false;
      setMessages([
        createMessage("assistant", userFacingApiError(error, "无法加载对话，请稍后重试。")),
      ]);
    });
  }, []);

  function followRun(runId: string): Promise<{ text: string; progress: ProgressStep[] }> {
    return new Promise((resolve, reject) => {
      const stream = new EventSource(`${apiUrl}/api/runs/${runId}/events/stream`, {
        withCredentials: true,
      });
      activeStreamRef.current = stream;
      const progress: ProgressStep[] = [];

      function finish(text: string) {
        stream.close();
        activeStreamRef.current = null;
        resolve({ text, progress });
      }

      const progressLabels: Record<string, string> = {
        run_created: "请求已进入队列",
        run_started: "正在理解你的安排",
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

      for (const [eventType, fallbackText] of Object.entries(progressLabels)) {
        stream.addEventListener(eventType, (event) => {
          const runEvent = JSON.parse((event as MessageEvent<string>).data) as RunEvent;
          const step = { eventType, text: runEvent.content ?? fallbackText };
          progress.push(step);
          setActiveProgress([...progress]);
        });
      }

      for (const eventType of ["run_completed", "clarification_requested"] as const) {
        stream.addEventListener(eventType, (event) => {
          const runEvent = JSON.parse((event as MessageEvent<string>).data) as RunEvent;
          finish(runEvent.content ?? "已处理完成。");
        });
      }

      stream.addEventListener("run_failed", (event) => {
        const runEvent = JSON.parse((event as MessageEvent<string>).data) as RunEvent;
        finish(runEvent.content ?? "请求没有成功。请稍后再试。");
      });
      stream.addEventListener("run_cancelled", (event) => {
        const runEvent = JSON.parse((event as MessageEvent<string>).data) as RunEvent;
        finish(runEvent.content ?? "请求已取消。");
      });
      stream.onerror = () => {
        stream.close();
        activeStreamRef.current = null;
        reject(new Error("Run event stream disconnected"));
      };
    });
  }

  async function refreshConversationState(resolvedThreadId: string) {
    const state = await getConversationState(resolvedThreadId);
    setConversationState(state);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const text = input.trim();
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

      setMessages((current) => [
        ...current,
        createMessage("assistant", result.text, result.progress, command.run_id),
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
      setMessages((current) => [
        ...current,
        createMessage("assistant", result.text, result.progress, command.run_id),
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

  return (
    <div className={styles.page}>
      <main className={styles.phone}>
        <header className={styles.header}>
          <div>
            <p className={styles.kicker}>Dayboard</p>
            <h1>日程助手</h1>
          </div>
          <div className={styles.headerActions}>
            <span className={styles.status}>在线</span>
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

        <section className={styles.messages} aria-label="对话记录">
          {messages.map((message) => (
            <article
              className={`${styles.message} ${
                message.role === "user" ? styles.userMessage : styles.assistantMessage
              }`}
              key={message.id}
            >
              <p>{message.text}</p>
              {message.progress?.length ? (
                <ol className={styles.progressList} aria-label="执行过程">
                  {message.progress.map((step, index) => (
                    <li key={`${step.eventType}-${index}`}>{step.text}</li>
                  ))}
                </ol>
              ) : null}
              {conversationState &&
              message.role === "assistant" &&
              message.runId === conversationState.state_data.source_run_id &&
              conversationState.state_data.interaction ? (
                <ClarificationInteraction
                  disabled={isSubmitting}
                  interaction={conversationState.state_data.interaction}
                  onSelect={handleClarificationChoice}
                />
              ) : null}
              <time>{message.time}</time>
            </article>
          ))}
          {isSubmitting ? (
            <article className={`${styles.message} ${styles.assistantMessage}`}>
              <p>{activeProgress.length ? "正在处理你的安排" : "正在提交请求"}</p>
              {activeProgress.length ? (
                <ol className={styles.progressList} aria-label="当前执行过程">
                  {activeProgress.map((step, index) => (
                    <li key={`${step.eventType}-${index}`}>{step.text}</li>
                  ))}
                </ol>
              ) : null}
            </article>
          ) : null}
        </section>

        <div className={styles.composerDock}>
          <form className={styles.composer} onSubmit={handleSubmit}>
            <button className={styles.iconButton} type="button" aria-label="语音输入">
              <Mic size={20} strokeWidth={2.2} />
            </button>
            <label className={styles.inputWrap}>
              <span className={styles.srOnly}>输入日程或任务</span>
              <input
                disabled={isSubmitting || !threadId}
                onChange={(event) => setInput(event.target.value)}
                placeholder="输入或按住说出你的安排"
                type="text"
                value={input}
              />
            </label>
            {isSubmitting ? (
              <button
                className={styles.stopButton}
                disabled={!activeRunId}
                onClick={handleCancel}
                type="button"
                aria-label="停止"
              >
                <Square size={17} fill="currentColor" strokeWidth={2.2} />
              </button>
            ) : (
              <button
                className={styles.sendButton}
                disabled={!input.trim() || !threadId}
                type="submit"
                aria-label="发送"
              >
                <SendHorizontal size={20} strokeWidth={2.2} />
              </button>
            )}
          </form>
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
