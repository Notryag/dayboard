"use client";

import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  MessageCircle,
} from "lucide-react";
import { AuthBoundary } from "@/features/auth/AuthBoundary";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthProvider";
import { userFacingApiError } from "@/lib/api/client";
import {
  RunActivityTicker,
} from "@/features/chat/RunActivityTicker";
import { ConversationBootstrapNotice } from "@/features/chat/ConversationBootstrapNotice";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import { useConversationSession } from "@/features/chat/useConversationSession";
import { Composer, type InputMode } from "@/features/chat/Composer";
import { SchedulePanel } from "@/features/schedule/SchedulePanel";
import { ScheduleSettingsDrawer } from "@/features/schedule/ScheduleSettingsDrawer";
import { ScheduleUndoToast } from "@/features/schedule/ScheduleUndoToast";
import { ReminderCenter } from "@/features/reminders/ReminderCenter";
import type { ReminderFocusTarget } from "@/features/reminders/types";
import type { ScheduleChange } from "@/features/schedule/types";
import styles from "@/app/page.module.css";

type PrimaryView = "chat" | "schedule";

type UndoNotice = NonNullable<ScheduleChange["undo"]> & {
  id: string;
  busy: boolean;
  error: string | null;
};

function ChatHome() {
  const { account, logout } = useAuth();
  const {
    activeRunId,
    bootstrapError,
    cancelActiveRun,
    chooseClarification,
    conversationState,
    isSubmitting,
    isThreadBootstrapping,
    markScheduleChanged,
    messages,
    progress: activeProgress,
    retryBootstrap,
    scheduleRevision,
    submitCommand,
    threadId,
  } = useConversationSession();
  const [input, setInput] = useState("");
  const [activeView, setActiveView] = useState<PrimaryView>("chat");
  const [inputMode, setInputMode] = useState<InputMode>("voice");
  const [undoNotice, setUndoNotice] = useState<UndoNotice | null>(null);
  const [reminderFocus, setReminderFocus] = useState<ReminderFocusTarget | null>(null);
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

  function handleScheduleChanged(change?: ScheduleChange) {
    markScheduleChanged();
    if (change?.undo) {
      setUndoNotice({
        ...change.undo,
        id: crypto.randomUUID(),
        busy: false,
        error: null,
      });
    }
  }

  function openReminderSource(target: Omit<ReminderFocusTarget, "requestId">) {
    setReminderFocus({ ...target, requestId: Date.now() });
    setActiveView("schedule");
  }

  async function handleUndo() {
    const notice = undoNotice;
    if (!notice || notice.busy) return;
    setUndoNotice({ ...notice, busy: true, error: null });
    try {
      await notice.run();
      markScheduleChanged();
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
    setActiveView(view);
    if (view === "schedule") markScheduleChanged();
  }

  return (
    <div className={styles.page}>
      <main className={styles.appShell}>
        <header className={styles.appHeader}>
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
            <ReminderCenter onOpenSource={openReminderSource} timezone={timezone} />
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
              onClarificationChoice={(optionKey) => void chooseClarification(optionKey)}
              scrollRef={messagesRef}
              timezone={timezone}
            />

            <div className={styles.composerDock}>
              {bootstrapError ? (
                <ConversationBootstrapNotice
                  busy={isThreadBootstrapping}
                  error={bootstrapError}
                  onRetry={retryBootstrap}
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
                onCancelRun={() => void cancelActiveRun()}
                onChange={setInput}
                onInputModeChange={setInputMode}
                onSubmit={(text) => {
                  if (!text.trim() || isSubmitting || !threadId) return;
                  setInput("");
                  void submitCommand(text);
                }}
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
              focusTarget={reminderFocus}
              key={reminderFocus?.requestId ?? "schedule"}
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
