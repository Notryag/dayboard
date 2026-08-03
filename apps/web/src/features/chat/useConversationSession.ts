"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getMessage, useI18n } from "@/i18n";
import type {
  ClarificationInteraction as Interaction,
  ConversationState,
} from "@/features/clarifications/types";
import { clarificationPresentation } from "@/features/clarifications/types";
import { apiBaseUrl, userFacingApiError } from "@/lib/api/client";
import {
  cancelRun,
  createCommandRun,
  getActiveRun,
  getConversationState,
  getPrimaryConversation,
  getThreadMessages,
  submitClarificationChoice,
} from "./api";
import { createMessage, initialMessages, persistedMessage } from "./conversationMessages";
import { useRunStream } from "./useRunStream";

function clarificationChoiceLabel(interaction: Interaction, optionKey: string, locale: "zh-CN" | "en-US") {
  if (interaction.type === "suggested_choice") {
    const option = interaction.options.find((candidate) => candidate.key === optionKey);
    return option ? getMessage(locale, "chat.selectOption", { label: option.label }) : null;
  }
  const option = interaction.options.find((candidate) => candidate.key === optionKey);
  if (!option) return null;
  const time = option.start_time ? new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: option.timezone,
  }).format(new Date(option.start_time)) : `${option.scheduled_date} · ${getMessage(locale, "schedule.anytime")}`;
  return getMessage(locale, "chat.selectOptionWithTime", { title: option.title, time });
}

export function useConversationSession() {
  const { locale, t } = useI18n();
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
  const [isLoadingOlderMessages, setIsLoadingOlderMessages] = useState(false);
  const [nextMessageCursor, setNextMessageCursor] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const initializingThreadRef = useRef(false);
  const loadingOlderMessagesRef = useRef(false);

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
      const currentThread = await getPrimaryConversation();
      const resolvedThreadId = currentThread.id;

      const history = await getThreadMessages(resolvedThreadId);
      const state = await getConversationState(resolvedThreadId);
      setThreadId(resolvedThreadId);
      setConversationState(state);
      setNextMessageCursor(history.next_cursor);
      dispatch({
        type: "messages_replaced",
        messages: history.items.length
          ? history.items.map((message) => persistedMessage(message, locale))
          : initialMessages(locale),
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
        setBootstrapError(userFacingApiError(error, t("chat.bootstrapFailed"), locale));
      })
      .finally(() => setIsThreadBootstrapping(false));
  }, [bootstrapAttempt, consumeRun, dispatch, locale, t]);

  const submitCommand = useCallback(async (submittedText: string) => {
    const text = submittedText.trim();
    if (!text || isSubmitting || !threadId) return;

    setIsSubmitting(true);
    dispatch({ type: "progress_reset" });
    dispatch({ type: "message_appended", message: createMessage("user", text, undefined, undefined, locale) });
    try {
      const command = await createCommandRun(threadId, { message: text });
      await consumeRun(command.run_id, threadId);
    } catch (error) {
      dispatch({
        type: "message_appended",
        message: createMessage(
          "assistant",
          userFacingApiError(error, t("chat.requestFailed"), locale),
          undefined,
          undefined,
          locale,
        ),
      });
    } finally {
      setIsSubmitting(false);
      dispatch({ type: "progress_reset" });
      setActiveRunId(null);
    }
  }, [consumeRun, dispatch, isSubmitting, locale, t, threadId]);

  const chooseClarification = useCallback(async (optionKey: string) => {
    const interaction = clarificationPresentation(conversationState);
    if (!threadId || !conversationState || !interaction || isSubmitting) return;
    const choiceLabel = clarificationChoiceLabel(interaction, optionKey, locale);
    if (!choiceLabel) return;

    setIsSubmitting(true);
    dispatch({ type: "progress_reset" });
    dispatch({ type: "message_appended", message: createMessage("user", choiceLabel, undefined, undefined, locale) });
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
        message: createMessage("assistant", t("chat.staleChoice"), undefined, undefined, locale),
      });
    } finally {
      setIsSubmitting(false);
      dispatch({ type: "progress_reset" });
      setActiveRunId(null);
    }
  }, [consumeRun, conversationState, dispatch, isSubmitting, locale, refreshConversationState, t, threadId]);

  const cancelActiveRun = useCallback(async () => {
    if (!activeRunId) return;
    try {
      await cancelRun(activeRunId);
    } catch (error) {
      dispatch({
        type: "message_appended",
        message: createMessage(
          "assistant",
          userFacingApiError(error, t("chat.stopFailed"), locale),
          undefined,
          undefined,
          locale,
        ),
      });
    }
  }, [activeRunId, dispatch, locale, t]);

  const markScheduleChanged = useCallback(() => {
    dispatch({ type: "schedule_changed" });
  }, [dispatch]);

  const loadOlderMessages = useCallback(async () => {
    if (!threadId || !nextMessageCursor || loadingOlderMessagesRef.current) return;
    loadingOlderMessagesRef.current = true;
    setIsLoadingOlderMessages(true);
    try {
      const history = await getThreadMessages(threadId, nextMessageCursor);
      setNextMessageCursor(history.next_cursor);
      dispatch({
        type: "messages_prepended",
          messages: history.items.map((message) => persistedMessage(message, locale)),
      });
    } finally {
      loadingOlderMessagesRef.current = false;
      setIsLoadingOlderMessages(false);
    }
  }, [dispatch, locale, nextMessageCursor, threadId]);

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
    isLoadingOlderMessages,
    hasOlderMessages: nextMessageCursor !== null,
    loadOlderMessages,
    markScheduleChanged,
    messages,
    progress,
    retryBootstrap,
    scheduleRevision,
    submitCommand,
    threadId,
  };
}
