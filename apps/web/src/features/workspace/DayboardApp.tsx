"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  MessageCircle,
} from "lucide-react";
import { AuthBoundary } from "@/features/auth/AuthBoundary";
import { Button } from "@/components/ui/button";
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
} from "@/features/chat/RunActivityTicker";
import { ConversationBootstrapNotice } from "@/features/chat/ConversationBootstrapNotice";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import {
  createMessage,
  initialMessages,
  persistedMessage,
  type ConversationMessage,
} from "@/features/chat/conversationMessages";
import { useRunStream } from "@/features/chat/useRunStream";
import { Composer, type InputMode } from "@/features/chat/Composer";
import { SchedulePanel } from "@/features/schedule/SchedulePanel";
import { ScheduleSettingsDrawer } from "@/features/schedule/ScheduleSettingsDrawer";
import { ScheduleUndoToast } from "@/features/schedule/ScheduleUndoToast";
import type { ScheduleChange } from "@/features/schedule/types";
import type {
  AgentRun,
  CommandRequest,
  CommandRun,
  ConversationThread,
  ThreadCreate,
} from "@/lib/api/types";
import styles from "@/app/page.module.css";

type PrimaryView = "chat" | "schedule";

type UndoNotice = NonNullable<ScheduleChange["undo"]> & {
  id: string;
  busy: boolean;
  error: string | null;
};

function clarificationChoiceLabel(interaction: Interaction, optionKey: string) {
  if (interaction.type === "suggested_choice") {
    const option = interaction.options.find((candidate) => candidate.key === optionKey);
    return option ? `选择“${option.label}”` : null;
  }
  const option = interaction.options.find((candidate) => candidate.key === optionKey);
  if (!option) return null;
  const time = option.start_time ? new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: option.timezone,
  }).format(new Date(option.start_time)) : `${option.scheduled_date} · 随时`;
  return `选择“${option.title} · ${time}”`;
}

function ChatHome() {
  const { account, logout } = useAuth();
  const apiUrl = useMemo(apiBaseUrl, []);
  const {
    state: { messages, progress: activeProgress, scheduleRevision },
    dispatch,
    followRun,
  } = useRunStream(apiUrl);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState<ConversationState | null>(null);
  const [activeView, setActiveView] = useState<PrimaryView>("chat");
  const [inputMode, setInputMode] = useState<InputMode>("voice");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [isThreadBootstrapping, setIsThreadBootstrapping] = useState(true);
  const [undoNotice, setUndoNotice] = useState<UndoNotice | null>(null);
  const [chatHeaderHidden, setChatHeaderHidden] = useState(false);
  const initializingThreadRef = useRef(false);
  const lastChatScrollTopRef = useRef(0);
  const messagesRef = useRef<HTMLElement>(null);

  const timezone = account?.timezone ?? "Asia/Shanghai";

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
        body: JSON.stringify({} satisfies ThreadCreate),
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
      dispatch({
        type: "messages_replaced",
        messages: history.length ? history.map(persistedMessage) : initialMessages,
      });

      const activeResponse = await apiFetch(
        `/api/threads/${resolvedThreadId}/active-run`,
      );
      const activeRun = (await activeResponse.json()) as AgentRun | null;
      if (activeRun) {
        setIsSubmitting(true);
        dispatch({ type: "progress_reset" });
        setActiveRunId(activeRun.id);
        try {
          const result = await followRun(activeRun.id, resolvedThreadId);
          await refreshConversationState(resolvedThreadId);
          dispatch({ type: "schedule_changed" });
          dispatch({ type: "run_result_received", runId: activeRun.id, text: result });
        } finally {
          setIsSubmitting(false);
          dispatch({ type: "progress_reset" });
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
    dispatch({ type: "progress_reset" });
    dispatch({ type: "message_appended", message: createMessage("user", text) });

    try {
      const response = await apiFetch(`/api/threads/${threadId}/command-runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ message: text } satisfies CommandRequest),
      });

      const command = (await response.json()) as CommandRun;
      setActiveRunId(command.run_id);
      const result = await followRun(command.run_id, threadId);

      await refreshConversationState(threadId);
      dispatch({ type: "schedule_changed" });
      dispatch({ type: "run_result_received", runId: command.run_id, text: result });
    } catch (error) {
      dispatch({
        type: "message_appended",
        message: createMessage(
          "assistant",
          userFacingApiError(error, "请求没有成功。请稍后再试。"),
        ),
      });
    } finally {
      setIsSubmitting(false);
      dispatch({ type: "progress_reset" });
      setActiveRunId(null);
    }
  }

  async function handleClarificationChoice(optionKey: string) {
    const interaction = conversationState?.state_data.interaction;
    if (!threadId || !interaction || isSubmitting) return;
    const choiceLabel = clarificationChoiceLabel(interaction, optionKey);
    if (!choiceLabel) return;

    setIsSubmitting(true);
    dispatch({ type: "progress_reset" });
    dispatch({ type: "message_appended", message: createMessage("user", choiceLabel) });
    try {
      const command = await submitClarificationChoice(threadId, {
        state_version: conversationState.version,
        option_key: optionKey,
      });
      setActiveRunId(command.run_id);
      const result = await followRun(command.run_id, threadId);
      await refreshConversationState(threadId);
      dispatch({ type: "schedule_changed" });
      dispatch({ type: "run_result_received", runId: command.run_id, text: result });
    } catch {
      await refreshConversationState(threadId).catch(() => undefined);
      dispatch({
        type: "message_appended",
        message: createMessage("assistant", "这个选项已经失效，请重新选择。"),
      });
    } finally {
      setIsSubmitting(false);
      dispatch({ type: "progress_reset" });
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
      dispatch({
        type: "message_appended",
        message: createMessage("assistant", userFacingApiError(error, "暂时无法停止，请稍后重试。")),
      });
    }
  }

  function handleScheduleChanged(change?: ScheduleChange) {
    dispatch({ type: "schedule_changed" });
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
      dispatch({ type: "schedule_changed" });
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
    if (view === "schedule") dispatch({ type: "schedule_changed" });
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
            <Button
              aria-label={activeView === "chat" ? "打开日程" : "返回对话"}
              className={styles.floatingHeaderButton}
              onClick={() => selectView(activeView === "chat" ? "schedule" : "chat")}
              size="icon"
              title={activeView === "chat" ? "日程" : "对话"}
              type="button"
              variant="ghost"
            >
              {activeView === "chat" ? (
                <CalendarDays aria-hidden="true" size={19} />
              ) : (
                <MessageCircle aria-hidden="true" size={19} />
              )}
            </Button>
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

export function DayboardApp() {
  return (
    <AuthBoundary>
      <ChatHome />
    </AuthBoundary>
  );
}
