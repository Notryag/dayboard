import { expect, test, type Page } from "@playwright/test";
import {
  calendarEntry,
  installApiFixture,
  schedulePart,
  terminalEvents,
} from "./api-fixture";

async function openTextComposer(page: Page) {
  await page.getByRole("button", { name: "切换到键盘输入" }).click();
  return page.getByPlaceholder("输入日程或任务");
}

test("register, login, and create a conversation thread", async ({ page }) => {
  const state = await installApiFixture(page, { account: null });
  await page.goto("/dayboard");
  await page.getByRole("button", { name: "注册" }).click();
  await page.getByLabel("用户名").fill("e2e-user");
  await page.getByLabel("密码", { exact: true }).fill("correct-horse-battery");
  await page.getByRole("textbox", { name: "确认密码" }).fill("correct-horse-battery");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
  await expect.poll(() => state.threadId).not.toBeNull();

  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await page.evaluate(() => localStorage.removeItem("dayboard.thread_id"));
  await page.getByLabel("账号操作").getByRole("button", { name: "登录" }).click();
  await page.getByLabel("用户名或邮箱").fill("e2e-user");
  await page.getByRole("textbox", { name: "密码" }).fill("correct-horse-battery");
  await page.locator("form").getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
  expect(state.requests.some((request) => request.path === "/api/auth/register")).toBeTruthy();
  expect(state.requests.some((request) => request.path === "/api/auth/login")).toBeTruthy();
  expect(state.requests.filter((request) => request.path === "/api/threads")).toHaveLength(2);
});

test("multiple arrangements stream into separate schedule cards", async ({ page }) => {
  const first = calendarEntry({ id: "calendar-a", title: "项目晨会" });
  const second = calendarEntry({
    id: "calendar-b",
    title: "客户访谈",
    start_time: "2026-07-21T15:00:00+08:00",
    end_time: "2026-07-21T16:00:00+08:00",
  });
  const parts = [schedulePart(first, "tool-a"), schedulePart(second, "tool-b")];
  const state = await installApiFixture(page);
  state.onCommand = () => ({ events: terminalEvents(parts), parts, persistedText: "安排好了。" });
  await page.goto("/dayboard");
  const input = await openTextComposer(page);
  await input.fill("明天九点开晨会，下午三点做客户访谈");
  await page.getByRole("button", { name: "发送" }).click();
  const results = page.getByLabel("本次安排");
  await expect(results.getByText("项目晨会")).toBeVisible();
  await expect(results.getByText("客户访谈")).toBeVisible();
  await expect(results.getByRole("button", { name: /完成/ })).toHaveCount(0);
});

test("reload restores history and rejoins an active Run", async ({ page }) => {
  const entry = calendarEntry({ id: "calendar-active", title: "恢复后的日程" });
  const part = schedulePart(entry, "tool-active");
  const state = await installApiFixture(page, {
    activeRun: { id: "run-active", status: "running", result_message: null },
    messages: [{
      id: "history-user",
      thread_id: "thread-existing",
      run_id: "run-old",
      role: "user",
      content: "昨天的历史消息",
      message_metadata: {},
      created_at: "2026-07-20T08:00:00Z",
    }],
    threadId: "thread-existing",
  });
  state.runs.set("run-active", {
    delayMs: 300,
    events: terminalEvents([part], "恢复执行完成。"),
    parts: [part],
    persistedText: "恢复执行完成。",
  });
  await page.addInitScript(() => localStorage.setItem("dayboard.thread_id", "thread-existing"));
  await page.goto("/dayboard");
  await expect(page.getByText("昨天的历史消息")).toBeVisible();
  await expect(page.getByText("恢复后的日程")).toBeVisible();
  expect(state.requests.some((request) => request.path.endsWith("/active-run"))).toBeTruthy();
  expect(state.requests.some((request) => request.path === "/api/runs/run-active/events/stream")).toBeTruthy();
});

test("calendar edit uses optimistic versions and can be undone", async ({ page }) => {
  const original = calendarEntry({ title: "产品评审" });
  const state = await installApiFixture(page, { calendars: [original] });
  await page.goto("/dayboard");
  await page.getByRole("button", { name: /查看日程：产品评审/ }).click();
  await page.getByRole("button", { name: "修改" }).click();
  await page.getByLabel("标题").fill("产品终审");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("已修改“产品评审”")).toBeVisible();
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.getByRole("button", { name: /查看日程：产品评审/ })).toBeVisible();

  const updates = state.requests.filter(
    (request) => request.method === "PUT" && request.path === "/api/calendar-entries/calendar-1",
  );
  expect(updates).toHaveLength(2);
  expect((updates[0].body as Record<string, unknown>).expected_updated_at).toBe(original.updated_at);
  expect((updates[1].body as Record<string, unknown>).expected_updated_at).not.toBe(original.updated_at);
});

test("clarification choice resumes execution and writes the final item", async ({ page }) => {
  const entry = calendarEntry({ id: "calendar-choice", title: "设计评审" });
  const part = schedulePart(entry, "tool-choice");
  const state = await installApiFixture(page);
  state.onCommand = (_message, fixture, runId) => {
    fixture.clarification = {
      thread_id: fixture.threadId,
      pending_action: "choose_time",
      pending_question: "几点进行设计评审？",
      state_data: {
        source_run_id: runId,
        interaction: {
          type: "suggested_choice",
          options: [
            { key: "morning", label: "上午 9 点" },
            { key: "afternoon", label: "下午 2 点" },
          ],
        },
      },
      version: 1,
      expires_at: null,
      updated_at: "2026-07-21T08:00:00Z",
    };
    return {
      events: [{
        type: "clarification_requested",
        data: { content: "几点进行设计评审？", parts: [] },
      }],
      persistedText: "几点进行设计评审？",
    };
  };
  state.onClarification = (optionKey) => {
    expect(optionKey).toBe("morning");
    state.calendars.push(entry);
    return { events: terminalEvents([part]), parts: [part], persistedText: "安排好了。" };
  };

  await page.goto("/dayboard");
  const input = await openTextComposer(page);
  await input.fill("安排设计评审");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("几点进行设计评审？")).toBeVisible();
  await page.getByRole("button", { name: "上午 9 点" }).click();
  await expect(page.getByRole("button", { name: "查看日程：设计评审" })).toBeVisible();
  expect(state.calendars).toHaveLength(1);
  expect(state.requests.some((request) => request.path.endsWith("/clarification-responses"))).toBeTruthy();
});

test("fixed audio is transcribed and submitted without a real microphone", async ({ page }) => {
  await page.addInitScript(() => {
    const fixedAudio = new Uint8Array([82, 73, 70, 70, 4, 0, 0, 0, 87, 65, 86, 69]);
    const stream = { getTracks: () => [{ stop: () => undefined }] };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => stream },
    });

    class FixedAudioRecorder {
      static isTypeSupported() { return true; }
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onerror: (() => void) | null = null;
      onstop: (() => void) | null = null;
      state = "inactive";
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob([fixedAudio], { type: this.mimeType }) });
        this.onstop?.();
      }
    }
    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      value: FixedAudioRecorder,
    });
  });

  const entry = calendarEntry({ id: "calendar-voice", title: "周会" });
  const part = schedulePart(entry, "tool-voice");
  const state = await installApiFixture(page, { voiceAvailable: true });
  state.onCommand = (message) => {
    expect(message).toBe("明天上午九点开周会");
    return { events: terminalEvents([part]), parts: [part], persistedText: "安排好了。" };
  };

  await page.goto("/dayboard");
  const recordButton = page.getByRole("button", { name: "按住说话" });
  await expect(recordButton).toBeEnabled();
  await recordButton.dispatchEvent("pointerdown", { button: 0, pointerId: 1 });
  await expect(page.getByRole("button", { name: /松开发送/ })).toBeVisible();
  await page.getByRole("button", { name: /松开发送/ }).dispatchEvent("pointerup", {
    button: 0,
    pointerId: 1,
  });
  await expect(page.getByRole("button", { name: "查看日程：周会" })).toBeVisible();
  const upload = state.requests.find((request) => request.path === "/api/voice/transcriptions");
  expect(upload?.method).toBe("POST");
  expect(String(upload?.body)).toContain("command-");
});
