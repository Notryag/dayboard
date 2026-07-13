"use client";

import type { RefObject } from "react";
import { Sparkles } from "lucide-react";
import { ClarificationInteraction } from "@/features/clarifications/ClarificationInteraction";
import type { ConversationState } from "@/features/clarifications/types";
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
  onClarificationChoice: (optionKey: string) => void;
  scrollRef: RefObject<HTMLElement | null>;
};

export function ChatMessageList({
  conversationState,
  isSubmitting,
  messages,
  onClarificationChoice,
  scrollRef,
}: ChatMessageListProps) {
  return (
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
            >
              <p>{message.text}</p>
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
            </article>
          </div>
        );
      })}
    </section>
  );
}
