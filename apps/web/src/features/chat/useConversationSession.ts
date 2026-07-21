"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ClarificationInteraction as Interaction,
  ConversationState,
} from "@/features/clarifications/types";
import { ApiError, apiBaseUrl, userFacingApiError } from "@/lib/api/client";
import type { ConversationMessage } from "@/lib/api/types";
import {
  cancelRun,
  createCommandRun,
  createThread,
  getActiveRun,
  getConversationState,
  getThreadMessages,
  submitClarificationChoice,
} from "./api";
import { createMessage, initialMessages, persistedMessage } from "./conversationMessages";
import { useRunStream } from "./useRunStream";

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

export function useConversationSession() {
  const apiUrl = useMemo(() => apiBaseUrl(), []);
  const {
    state: { messages, progress, scheduleRevision },
    dispatch,
    followRun,
  } = useRunStream(apiUrl);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [conversationState, setConversationState] = useState<ConversationState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isThreadBootstrapping, setIsThreadBootstrapping] = useState(true);
  const [threadId, setThreadId] = useState<string | null>(null);
  const initializingThreadRef = useRef(false);

  const refreshConversationState = useCallback(async (resolvedThreadId: string) => {
    setConversationState(await getConversationState(resolvedThreadId));
  }, []);

  const consumeRun = useCallback(async (runId: string, resolvedThreadId: string) => {
    setActiveRunId(runId);
    const result = await followRun(runId, resolvedThreadId);
    await refreshConversationState(resolvedThreadId);
    dispatch({ type: "schedule_changed" });
    dispatch({ type: "run_result_received", runId, text: result });
  }, [dispatch, followRun, refreshConversationState]);

  useEffect(() => {
    if (initializingThreadRef.current) return;
    initializingThreadRef.current = true;
    setBootstrapError(null);
    setIsThreadBootstrapping(true);

    async function initializeThread() {
      let resolvedThreadId = localStorage.getItem("dayboard.thread_id");
      let history: ConversationMessage[] = [];
      if (resolvedThreadId) {
        try {
          history = await getThreadMessages(resolvedThreadId);
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            localStorage.removeItem("dayboard.thread_id");
            resolvedThreadId = null;
          } else {
            throw error;
          }
        }
      }
      if (!resolvedThreadId) {
        const thread = await createThread();
        resolvedThreadId = thread.id;
        localStorage.setItem("dayboard.thread_id", resolvedThreadId);
      }

      const state = await getConversationState(resolvedThreadId);
      setThreadId(resolvedThreadId);
      setConversationState(state);
      dispatch({
        type: "messages_replaced",
        messages: history.length ? history.map(persistedMessage) : initialMessages,
      });

      const activeRun = await getActiveRun(resolvedThreadId);
      if (!activeRun) return;
      setIsSubmitting(true);
      dispatch({ type: "progress_reset" });
      try {
        await consumeRun(activeRun.id, resolvedThreadId);
      } finally {
        setIsSubmitting(false);
        dispatch({ type: "progress_reset" });
        setActiveRunId(null);
      }
    }

    void initializeThread()
      .catch((error: unknown) => {
        initializingThreadRef.current = false;
        setBootstrapError(userFacingApiError(error, "无法加载对话，请稍后重试。"));
      })
      .finally(() => setIsThreadBootstrapping(false));
  }, [bootstrapAttempt, consumeRun, dispatch]);

  const submitCommand = useCallback(async (submittedText: string) => {
    const text = submittedText.trim();
    if (!text || isSubmitting || !threadId) return;

    setIsSubmitting(true);
    dispatch({ type: "progress_reset" });
    dispatch({ type: "message_appended", message: createMessage("user", text) });
    try {
      const command = await createCommandRun(threadId, { message: text });
      await consumeRun(command.run_id, threadId);
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
  }, [consumeRun, dispatch, isSubmitting, threadId]);

  const chooseClarification = useCallback(async (optionKey: string) => {
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
      await consumeRun(command.run_id, threadId);
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
  }, [consumeRun, conversationState, dispatch, isSubmitting, refreshConversationState, threadId]);

  const cancelActiveRun = useCallback(async () => {
    if (!activeRunId) return;
    try {
      await cancelRun(activeRunId);
    } catch (error) {
      dispatch({
        type: "message_appended",
        message: createMessage(
          "assistant",
          userFacingApiError(error, "暂时无法停止，请稍后重试。"),
        ),
      });
    }
  }, [activeRunId, dispatch]);

  const markScheduleChanged = useCallback(() => {
    dispatch({ type: "schedule_changed" });
  }, [dispatch]);

  const retryBootstrap = useCallback(() => {
    setBootstrapAttempt((current) => current + 1);
  }, []);

  return {
    activeRunId,
    bootstrapError,
    cancelActiveRun,
    chooseClarification,
    conversationState,
    isSubmitting,
    isThreadBootstrapping,
    markScheduleChanged,
    messages,
    progress,
    retryBootstrap,
    scheduleRevision,
    submitCommand,
    threadId,
  };
}
