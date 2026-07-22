import { expect, test, type Page } from "@playwright/test";
import {
  calendarEntry,
  installApiFixture,
  schedulePart,
  taskItem,
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

test("calendar search streams every match before the assistant summary", async ({ page }) => {
  const first = calendarEntry({ id: "calendar-query-a", title: "明日晨会" });
  const second = calendarEntry({
    id: "calendar-query-b",
    title: "提交材料",
    timing_kind: "anytime",
    scheduled_date: "2026-07-23",
    start_time: null,
    end_time: null,
  });
  const parts = [schedulePart(first, "tool-query"), schedulePart(second, "tool-query")];
  const state = await installApiFixture(page);
  state.onCommand = () => ({
    events: [
      { type: "schedule_items_result", data: { tool_call_id: "tool-query", parts } },
      { type: "run_completed", data: { content: "明天有 2 项日程。", parts } },
    ],
    parts,
    persistedText: "明天有 2 项日程。",
  });
  await page.goto("/dayboard");
  const input = await openTextComposer(page);
  await input.fill("我明天有什么日程");
  await page.getByRole("button", { name: "发送" }).click();

  const results = page.getByLabel("本次安排");
  await expect(results.getByText("明日晨会")).toBeVisible();
  await expect(results.getByText("提交材料")).toBeVisible();
  await expect(
    results.locator("xpath=following-sibling::*").getByText("明天有 2 项日程。"),
  ).toBeVisible();
  await expect(results.getByRole("button", { name: /完成/ })).toHaveCount(0);
});

test("mobile viewport keeps the transparent header visible while chat scrolls", async ({ page }) => {
  const messages = Array.from({ length: 24 }, (_, index) => ({
    id: `history-${index}`,
    thread_id: "thread-existing",
    run_id: `run-${index}`,
    role: "user" as const,
    content: `历史安排 ${index + 1}：这是一条用于验证移动端滚动区域的较长消息。`,
    message_metadata: {},
    created_at: `2026-07-20T${String(index).padStart(2, "0")}:00:00Z`,
  }));
  await page.setViewportSize({ width: 390, height: 844 });
  await installApiFixture(page, { messages, threadId: "thread-existing" });
  await page.addInitScript(() => localStorage.setItem("dayboard.thread_id", "thread-existing"));
  await page.goto("/dayboard");

  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
    "content",
    /viewport-fit=cover/,
  );
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
    "content",
    /minimum-scale=1.*maximum-scale=1.*user-scalable=no/,
  );
  const header = page.locator("header").first();
  await expect(header).toBeVisible();
  await expect.poll(() => page.locator("main").evaluate((appShell) => {
    const pageRoot = appShell.parentElement;
    return new Set([
      getComputedStyle(document.documentElement).backgroundColor,
      getComputedStyle(document.body).backgroundColor,
      pageRoot ? getComputedStyle(pageRoot).backgroundColor : "missing",
      getComputedStyle(appShell).backgroundColor,
    ]).size;
  })).toBe(1);
  const messagesRegion = page.getByRole("region", { name: "对话记录" });
  await messagesRegion.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event("scroll"));
  });
  await expect.poll(() => header.evaluate((element) => ({
    opacity: getComputedStyle(element).opacity,
    transform: getComputedStyle(element).transform,
  }))).toEqual({ opacity: "1", transform: "none" });
});

test("mobile content swipe switches between conversation and schedule", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApiFixture(page);
  await page.goto("/dayboard");
  const workspace = page.locator("[data-active-view]");
  const track = page.locator("[data-view-track]");
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
  await expect.poll(() => track.evaluate((element) => {
    const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
    return matrix.m41;
  })).toBeLessThan(-380);
  await expect.poll(async () => {
    const box = await page.locator("#schedule-panel").boundingBox();
    return box ? box.x + box.width : Number.POSITIVE_INFINITY;
  }).toBeLessThanOrEqual(1);

  await page.mouse.move(300, 360);
  await page.mouse.down();
  await page.mouse.move(365, 361, { steps: 3 });
  await page.mouse.move(380, 363, { steps: 3 });
  await page.mouse.up();
  await expect(workspace).toHaveAttribute("data-active-view", "schedule");
  await expect(page.getByRole("region", { name: "日程", exact: true })).toBeVisible();

  await expect.poll(() => track.evaluate((element) => {
    const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
    return matrix.m41;
  })).toBeGreaterThan(-10);
  await page.mouse.move(90, 520);
  await page.mouse.down();
  await page.mouse.move(45, 519, { steps: 3 });
  await page.mouse.move(10, 517, { steps: 3 });
  await page.mouse.up();
  await expect(workspace).toHaveAttribute("data-active-view", "chat");
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
});

test("desktop switches between full-screen conversation and schedule", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await installApiFixture(page);
  await page.goto("/dayboard");

  const chatBox = await page.locator("#chat-panel").boundingBox();
  const scheduleBox = await page.locator("#schedule-panel").boundingBox();
  expect(chatBox).not.toBeNull();
  expect(scheduleBox).not.toBeNull();
  expect(chatBox!.width).toBeCloseTo(1200, 0);
  expect(scheduleBox!.width).toBeCloseTo(1200, 0);
  await expect.poll(async () => (await page.locator("#chat-panel").boundingBox())?.x).toBeCloseTo(0, 0);
  await expect.poll(async () => {
    const box = await page.locator("#schedule-panel").boundingBox();
    return box ? box.x + box.width : Number.POSITIVE_INFINITY;
  }).toBeLessThanOrEqual(1);
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "日程", exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "打开日程" }).click();
  await expect(page.getByRole("region", { name: "日程", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "对话", exact: true })).toHaveCount(0);
  await expect.poll(async () => (await page.locator("#schedule-panel").boundingBox())?.x).toBeCloseTo(0, 0);
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
  await page.getByRole("button", { name: "打开日程" }).click();
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

test("completed task remains visible in the schedule", async ({ page }) => {
  const task = taskItem();
  const state = await installApiFixture(page, { tasks: [task] });
  await page.goto("/dayboard");
  await page.getByRole("button", { name: "打开日程" }).click();

  await page.getByRole("button", { name: "完成待办：整理资料" }).click();
  const completed = page.getByRole("button", { name: "已完成待办：整理资料" });
  await expect(completed).toBeVisible();
  await expect(completed).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => state.tasks[0]?.status).toBe("completed");

  const listRequests = state.requests.filter(
    (request) => request.method === "GET" && request.path === "/api/task-items",
  );
  expect(listRequests.length).toBeGreaterThan(0);
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

test("unread reminder opens and focuses its schedule item", async ({ page }) => {
  const entry = calendarEntry({ title: "产品评审" });
  const state = await installApiFixture(page, {
    calendars: [entry],
    reminders: [{
      id: "reminder-1",
      tenant_id: "tenant-1",
      owner_user_id: "user-1",
      source_type: "calendar_entry",
      source_id: entry.id,
      channel: "in_app",
      scheduled_for: "2026-07-21T09:50:00+08:00",
      status: "delivered",
      attempt_count: 1,
      next_attempt_at: null,
      delivered_at: "2026-07-21T09:50:00+08:00",
      read_at: null,
      provider_message_id: "in_app:reminder-1",
      last_error: null,
      payload: {
        title: entry.title,
        occurs_at: entry.start_time,
        timezone: entry.timezone,
      },
      created_at: "2026-07-21T09:00:00+08:00",
      updated_at: "2026-07-21T09:50:00+08:00",
    }],
  });

  await page.goto("/dayboard");
  await page.getByRole("button", { name: "提醒，1 条未读" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("1 条未读")).toBeVisible();
  await drawer.getByRole("button", { name: /产品评审/ }).click();
  await expect(page.locator("[data-reminder-highlighted='true']")).toContainText("产品评审");
  await expect(page.getByRole("button", { name: "提醒", exact: true })).toBeVisible();
  expect(state.requests.some((request) => request.path === "/api/reminders/reminder-1/read")).toBeTruthy();
});
