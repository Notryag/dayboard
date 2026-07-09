import { Mic, SendHorizontal } from "lucide-react";
import styles from "./page.module.css";

const messages = [
  {
    id: "welcome",
    role: "assistant",
    text: "今天想安排什么？你可以直接说“明天下午三点提醒我开产品会”。",
    time: "09:20",
  },
  {
    id: "example-user",
    role: "user",
    text: "周五上午 10 点和 Alice 做一次项目复盘。",
    time: "09:21",
  },
  {
    id: "example-assistant",
    role: "assistant",
    text: "可以。我会创建一条周五上午 10:00 的日程。需要设置提醒吗？",
    time: "09:21",
  },
];

export default function Home() {
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
        </section>

        <div className={styles.composerDock}>
          <form className={styles.composer}>
            <button className={styles.iconButton} type="button" aria-label="语音输入">
              <Mic size={20} strokeWidth={2.2} />
            </button>
            <label className={styles.inputWrap}>
              <span className={styles.srOnly}>输入日程或任务</span>
              <input placeholder="输入或按住说出你的安排" type="text" />
            </label>
            <button className={styles.sendButton} type="button" aria-label="发送">
              <SendHorizontal size={20} strokeWidth={2.2} />
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
