"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Mic, SendHorizontal } from "lucide-react";
import styles from "./page.module.css";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  time: string;
};

type CommandRunResponse = {
  run_id: string;
  status: "queued";
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

function createMessage(role: ChatMessage["role"], text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: currentTimeLabel(),
  };
}

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const activeStreamRef = useRef<EventSource | null>(null);

  const apiBaseUrl = useMemo(() => {
    return process.env.NEXT_PUBLIC_DAYBOARD_API_BASE_URL ?? "http://127.0.0.1:8000";
  }, []);

  useEffect(() => {
    return () => activeStreamRef.current?.close();
  }, []);

  function followRun(runId: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const stream = new EventSource(`${apiBaseUrl}/api/runs/${runId}/events/stream`);
      activeStreamRef.current = stream;

      function finish(text: string) {
        stream.close();
        activeStreamRef.current = null;
        resolve(text);
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
      stream.onerror = () => {
        stream.close();
        activeStreamRef.current = null;
        reject(new Error("Run event stream disconnected"));
      };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const text = input.trim();
    if (!text || isSubmitting) {
      return;
    }

    setInput("");
    setIsSubmitting(true);
    setMessages((current) => [...current, createMessage("user", text)]);

    try {
      const response = await fetch(`${apiBaseUrl}/api/command-runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: text }),
      });

      if (!response.ok) {
        throw new Error(`Command request failed with ${response.status}`);
      }

      const command: CommandRunResponse = await response.json();
      const assistantText = await followRun(command.run_id);

      setMessages((current) => [...current, createMessage("assistant", assistantText)]);
    } catch {
      setMessages((current) => [
        ...current,
        createMessage("assistant", "请求没有成功。请稍后再试。"),
      ]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.phone}>
        <header className={styles.header}>
          <div>
            <p className={styles.kicker}>Dayboard</p>
            <h1>日程助手</h1>
          </div>
          <span className={styles.status}>在线</span>
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
              <time>{message.time}</time>
            </article>
          ))}
          {isSubmitting ? (
            <article className={`${styles.message} ${styles.assistantMessage}`}>
              <p>正在处理...</p>
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
                disabled={isSubmitting}
                onChange={(event) => setInput(event.target.value)}
                placeholder="输入或按住说出你的安排"
                type="text"
                value={input}
              />
            </label>
            <button
              className={styles.sendButton}
              disabled={!input.trim() || isSubmitting}
              type="submit"
              aria-label="发送"
            >
              <SendHorizontal size={20} strokeWidth={2.2} />
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
