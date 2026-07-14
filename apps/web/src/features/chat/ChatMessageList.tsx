"use client";

import {
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Copy, ScanText, Sparkles } from "lucide-react";
import { ClarificationInteraction } from "@/features/clarifications/ClarificationInteraction";
import type { ConversationState } from "@/features/clarifications/types";
import { getScheduleItemsByRunIds } from "@/features/schedule/api";
import { ScheduleItem } from "@/features/schedule/ScheduleItem";
import type { RunScheduleItemGroup, ScheduleDisplayItem } from "@/features/schedule/types";
import styles from "./ChatMessageList.module.css";

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  time: string;
  runId?: string;
};

type ChatMessageListProps = {
  conversationState: ConversationState | null;
  isSubmitting: boolean;
  messages: ChatMessage[];
  onChanged: () => void;
  onClarificationChoice: (optionKey: string) => void;
  onEdit: (item: ScheduleDisplayItem) => void;
  refreshKey: number;
  scrollRef: RefObject<HTMLElement | null>;
  timezone: string;
};

type MessageActionMenu = {
  messageId: string;
  placement: "above" | "below";
  text: string;
  x: number;
  y: number;
};

const longPressDurationMs = 450;
const longPressMoveTolerancePx = 10;
const autoScrollThresholdPx = 80;

function messageTextId(messageId: string) {
  return `chat-message-text-${messageId}`;
}

export function ChatMessageList({
  conversationState,
  isSubmitting,
  messages,
  onChanged,
  onClarificationChoice,
  onEdit,
  refreshKey,
  scrollRef,
  timezone,
}: ChatMessageListProps) {
  const [messageMenu, setMessageMenu] = useState<MessageActionMenu | null>(null);
  const [scheduleGroups, setScheduleGroups] = useState<Record<string, RunScheduleItemGroup>>({});
  const pressOriginRef = useRef<{ x: number; y: number } | null>(null);
  const pressTimerRef = useRef<number | null>(null);
  const assistantRunIds = useMemo(
    () => Array.from(new Set(messages.flatMap((message) =>
      message.role === "assistant" && message.runId ? [message.runId] : [],
    ))).slice(-50),
    [messages],
  );
  const assistantRunKey = assistantRunIds.join(",");

  useEffect(() => {
    const controller = new AbortController();
    if (!assistantRunIds.length) return () => controller.abort();
    const container = scrollRef.current;
    const shouldKeepBottom = container
      ? container.scrollHeight - container.scrollTop - container.clientHeight < autoScrollThresholdPx
      : false;
    void getScheduleItemsByRunIds(assistantRunIds, controller.signal)
      .then((groups) => {
        setScheduleGroups(Object.fromEntries(groups.map((group) => [group.run_id, group])));
        if (shouldKeepBottom) {
          window.requestAnimationFrame(() => {
            const currentContainer = scrollRef.current;
            if (currentContainer) currentContainer.scrollTop = currentContainer.scrollHeight;
          });
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [assistantRunKey, assistantRunIds, refreshKey, scrollRef]);

  function clearLongPress() {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
    pressOriginRef.current = null;
  }

  function openMessageMenu(message: ChatMessage, element: HTMLElement) {
    const rect = element.getBoundingClientRect();
    const placement = rect.top > 72 ? "above" : "below";
    setMessageMenu({
      messageId: message.id,
      placement,
      text: message.text,
      x: rect.left + rect.width / 2,
      y: placement === "above" ? rect.top : rect.bottom,
    });
  }

  function handlePointerDown(
    event: ReactPointerEvent<HTMLElement>,
    message: ChatMessage,
  ) {
    if (event.pointerType === "mouse" || event.button !== 0) return;
    if ((event.target as HTMLElement).closest("button, a, input, textarea, select")) return;

    clearLongPress();
    pressOriginRef.current = { x: event.clientX, y: event.clientY };
    const element = event.currentTarget;
    pressTimerRef.current = window.setTimeout(() => {
      pressTimerRef.current = null;
      pressOriginRef.current = null;
      navigator.vibrate?.(8);
      openMessageMenu(message, element);
    }, longPressDurationMs);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLElement>) {
    const origin = pressOriginRef.current;
    if (!origin) return;
    if (
      Math.abs(event.clientX - origin.x) > longPressMoveTolerancePx ||
      Math.abs(event.clientY - origin.y) > longPressMoveTolerancePx
    ) {
      clearLongPress();
    }
  }

  function handleContextMenu(
    event: ReactMouseEvent<HTMLElement>,
    message: ChatMessage,
  ) {
    if ((event.target as HTMLElement).closest("button, a, input, textarea, select")) return;
    event.preventDefault();
    clearLongPress();
    openMessageMenu(message, event.currentTarget);
  }

  async function copyMessageText() {
    if (!messageMenu) return;
    try {
      await navigator.clipboard.writeText(messageMenu.text);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = messageMenu.text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    setMessageMenu(null);
  }

  function selectMessageText() {
    if (!messageMenu) return;
    const selectedMessageId = messageMenu.messageId;
    setMessageMenu(null);
    window.requestAnimationFrame(() => {
      const textElement = document.getElementById(messageTextId(selectedMessageId));
      const selection = window.getSelection();
      if (!textElement || !selection) return;
      const range = document.createRange();
      range.selectNodeContents(textElement);
      selection.removeAllRanges();
      selection.addRange(range);
    });
  }

  useEffect(() => {
    return () => {
      if (pressTimerRef.current !== null) window.clearTimeout(pressTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!messageMenu) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setMessageMenu(null);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [messageMenu]);

  return (
    <>
      <section className={styles.messages} aria-label="对话记录" ref={scrollRef}>
        {messages.map((message) => {
          const isUser = message.role === "user";
          return (
            <div
              className={`${styles.messageRow} ${isUser ? styles.userRow : styles.assistantRow}`}
              key={message.id}
            >
              {!isUser ? (
                <span aria-hidden="true" className={styles.assistantMark}>
                  <Sparkles size={15} strokeWidth={2.2} />
                </span>
              ) : null}
              <article
                className={`${styles.message} ${
                  isUser ? styles.userMessage : styles.assistantMessage
                }`}
                onContextMenu={(event) => handleContextMenu(event, message)}
                onPointerCancel={clearLongPress}
                onPointerDown={(event) => handlePointerDown(event, message)}
                onPointerLeave={clearLongPress}
                onPointerMove={handlePointerMove}
                onPointerUp={clearLongPress}
              >
                <p id={messageTextId(message.id)}>{message.text}</p>
                {conversationState &&
                !isUser &&
                message.runId === conversationState.state_data.source_run_id &&
                conversationState.state_data.interaction ? (
                  <ClarificationInteraction
                    disabled={isSubmitting}
                    interaction={conversationState.state_data.interaction}
                    onSelect={onClarificationChoice}
                  />
                ) : null}
                <time>{message.time}</time>
                {!isUser && message.runId && scheduleGroups[message.runId]
                  ? [
                      ...scheduleGroups[message.runId].calendar_entries.map((entry) => ({
                        kind: "calendar" as const,
                        value: entry,
                      })),
                      ...scheduleGroups[message.runId].task_items.map((task) => ({
                        kind: "task" as const,
                        value: task,
                      })),
                    ].map((item) => (
                      <ScheduleItem
                        item={item}
                        key={`${item.kind}-${item.value.id}`}
                        onChanged={onChanged}
                        onEdit={onEdit}
                        timezone={timezone}
                        variant="chat"
                      />
                    ))
                  : null}
              </article>
            </div>
          );
        })}
      </section>

      {messageMenu
        ? createPortal(
            <div
              className={styles.messageMenuLayer}
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) setMessageMenu(null);
              }}
              role="presentation"
            >
              <div
                aria-label="消息操作"
                className={`${styles.messageMenu} ${
                  messageMenu.placement === "above"
                    ? styles.messageMenuAbove
                    : styles.messageMenuBelow
                }`}
                role="menu"
                style={
                  {
                    "--chat-menu-anchor-x": `${messageMenu.x}px`,
                    "--chat-menu-anchor-y": `${messageMenu.y}px`,
                  } as CSSProperties
                }
              >
                <button onClick={() => void copyMessageText()} role="menuitem" type="button">
                  <Copy aria-hidden="true" size={18} />
                  <span>复制</span>
                </button>
                <button onClick={selectMessageText} role="menuitem" type="button">
                  <ScanText aria-hidden="true" size={18} />
                  <span>选择文本</span>
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
