import type { Page, Route } from "@playwright/test";

type Json = Record<string, unknown>;

export type CalendarEntry = {
  id: string;
  title: string;
  timing_kind: "timed" | "anytime";
  scheduled_date: string | null;
  start_time: string | null;
  end_time: string | null;
  timezone: string;
  participants: string[];
  reminder: null;
  status: "scheduled" | "completed" | "cancelled";
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskItem = {
  id: string;
  title: string;
  due_at: string | null;
  timezone: string;
  reminder: null;
  status: "open" | "completed" | "cancelled";
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
};

export type RunSpec = {
  events: Array<{ type: string; data: Json }>;
  persistedText?: string;
  parts?: Json[];
  delayMs?: number;
};

export type ReminderDelivery = {
  id: string;
  source_type: "calendar_entry" | "task_item";
  source_id: string;
  scheduled_for: string;
  status: "pending" | "processing" | "delivered" | "failed" | "cancelled";
  read_at: string | null;
  payload: Record<string, unknown>;
  [key: string]: unknown;
};

type FixtureState = {
  account: Json | null;
  activeRun: Json | null;
  calendars: CalendarEntry[];
  clarification: Json | null;
  messages: Json[];
  requests: Array<{ method: string; path: string; body: unknown }>;
  reminders: ReminderDelivery[];
  runs: Map<string, RunSpec>;
  tasks: TaskItem[];
  threadId: string | null;
  voiceAvailable: boolean;
  voiceTranscript: string;
  onCommand?: (message: string, state: FixtureState, runId: string) => RunSpec;
  onClarification?: (optionKey: string, state: FixtureState) => RunSpec;
};

const now = "2026-07-21T08:00:00Z";

export function calendarEntry(overrides: Partial<CalendarEntry> = {}): CalendarEntry {
  return {
    id: "calendar-1",
    title: "产品评审",
    timing_kind: "timed",
    scheduled_date: null,
    start_time: "2026-07-21T10:00:00+08:00",
    end_time: "2026-07-21T11:00:00+08:00",
    timezone: "Asia/Shanghai",
    participants: [],
    reminder: null,
    status: "scheduled",
    created_by_run_id: "run-seed",
    created_at: now,
    updated_at: "2026-07-21T08:00:00Z",
    ...overrides,
  };
}

export function taskItem(overrides: Partial<TaskItem> = {}): TaskItem {
  return {
    id: "task-1",
    title: "整理资料",
    due_at: null,
    timezone: "Asia/Shanghai",
    reminder: null,
    status: "open",
    created_by_run_id: "run-seed",
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function account() {
  return {
    user_id: "user-1",
    tenant_id: "tenant-1",
    username: "e2e-user",
    email: "e2e@example.test",
    display_name: "E2E User",
    timezone: "Asia/Shanghai",
    locale: "zh-CN",
  };
}

function corsHeaders(contentType = "application/json") {
  return {
    "access-control-allow-credentials": "true",
    "access-control-allow-headers": "content-type,idempotency-key",
    "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
    "access-control-allow-origin": "http://127.0.0.1:3100",
    "content-type": contentType,
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    headers: corsHeaders(),
    status,
  });
}

function sseBody(events: RunSpec["events"]) {
  return events.map((event, index) => (
    `id: ${index + 1}-0\nevent: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`
  )).join("");
}

export async function installApiFixture(
  page: Page,
  initial: Partial<FixtureState> = {},
) {
  const state: FixtureState = {
    account: account(),
    activeRun: null,
    calendars: [],
    clarification: null,
    messages: [],
    requests: [],
    reminders: [],
    runs: new Map(),
    tasks: [],
    threadId: null,
    voiceAvailable: false,
    voiceTranscript: "明天上午九点开周会",
    ...initial,
  };
  let sequence = 0;

  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = request.headers()["content-type"]?.includes("application/json")
      ? request.postDataJSON()
      : request.postData();
    state.requests.push({ method, path, body });

    if (method === "OPTIONS") {
      await route.fulfill({ headers: corsHeaders(), status: 204 });
      return;
    }
    if (path === "/api/auth/capabilities") return json(route, { password_reset_available: true });
    if (path === "/api/auth/me") {
      return state.account
        ? json(route, state.account)
        : json(route, { error: { code: "AUTHENTICATION_REQUIRED", message: "Auth required" } }, 401);
    }
    if (path === "/api/auth/register" || path === "/api/auth/login") {
      state.account = account();
      return json(route, state.account);
    }
    if (path === "/api/auth/logout") {
      state.account = null;
      return json(route, { ok: true });
    }
    if (path === "/api/voice/capabilities") {
      return json(route, {
        available: state.voiceAvailable,
        max_duration_seconds: 60,
        max_upload_bytes: 5_000_000,
        supported_content_types: ["audio/webm"],
      });
    }
    if (path === "/api/voice/transcriptions" && method === "POST") {
      return json(route, {
        id: "transcript-1",
        text: state.voiceTranscript,
        language: "zh",
        duration_seconds: 1,
      });
    }
    if (path === "/api/threads" && method === "POST") {
      state.threadId = `thread-${++sequence}`;
      return json(route, {
        id: state.threadId,
        tenant_id: "tenant-1",
        owner_user_id: "user-1",
        title: null,
        expected_updated_at: now,
      });
    }
    const messagesMatch = path.match(/^\/api\/threads\/([^/]+)\/messages$/);
    if (messagesMatch) return json(route, state.messages);
    const stateMatch = path.match(/^\/api\/threads\/([^/]+)\/state$/);
    if (stateMatch) return json(route, state.clarification);
    const activeMatch = path.match(/^\/api\/threads\/([^/]+)\/active-run$/);
    if (activeMatch) return json(route, state.activeRun);
    const commandMatch = path.match(/^\/api\/threads\/([^/]+)\/command-runs$/);
    if (commandMatch && method === "POST") {
      const runId = `run-${++sequence}`;
      const message = String((body as Json).message);
      const spec = state.onCommand?.(message, state, runId) ?? {
        events: [{ type: "run_completed", data: { content: "已处理完成。", parts: [] } }],
      };
      state.runs.set(runId, spec);
      state.activeRun = { id: runId, status: "running", result_message: null };
      state.messages.push({
        id: `message-${sequence}-user`,
        thread_id: commandMatch[1],
        run_id: runId,
        role: "user",
        content: message,
        message_metadata: {},
        created_at: now,
      });
      if (spec.persistedText !== undefined) {
        state.messages.push({
          id: `message-${sequence}-assistant`,
          thread_id: commandMatch[1],
          run_id: runId,
          role: "assistant",
          content: spec.persistedText,
          message_metadata: { parts: spec.parts ?? [] },
          created_at: now,
        });
      }
      return json(route, { run_id: runId, status: "queued", thread_id: commandMatch[1] });
    }
    const clarificationMatch = path.match(/^\/api\/threads\/([^/]+)\/clarification-responses$/);
    if (clarificationMatch && method === "POST") {
      const runId = `run-${++sequence}`;
      const spec = state.onClarification?.(String((body as Json).option_key), state) ?? {
        events: [{ type: "run_completed", data: { content: "已处理完成。", parts: [] } }],
      };
      state.runs.set(runId, spec);
      state.activeRun = { id: runId, status: "running", result_message: null };
      state.clarification = null;
      return json(route, { run_id: runId, status: "queued", thread_id: clarificationMatch[1] });
    }
    const streamMatch = path.match(/^\/api\/runs\/([^/]+)\/events\/stream$/);
    if (streamMatch) {
      const spec = state.runs.get(streamMatch[1]);
      if (!spec) return json(route, { error: { code: "RUN_NOT_FOUND" } }, 404);
      if (spec.delayMs) await new Promise((resolve) => setTimeout(resolve, spec.delayMs));
      state.activeRun = null;
      await route.fulfill({
        body: sseBody(spec.events),
        headers: corsHeaders("text/event-stream"),
        status: 200,
      });
      return;
    }
    const runMatch = path.match(/^\/api\/runs\/([^/]+)$/);
    if (runMatch) return json(route, state.activeRun ?? { id: runMatch[1], status: "completed", result_message: "已处理完成。" });
    if (path === "/api/reminders" && method === "GET") return json(route, state.reminders);
    const reminderRead = path.match(/^\/api\/reminders\/([^/]+)\/read$/);
    if (reminderRead && method === "POST") {
      const reminder = state.reminders.find((item) => item.id === reminderRead[1]);
      if (!reminder) return json(route, { error: { code: "REMINDER_NOT_FOUND" } }, 404);
      reminder.read_at = now;
      return json(route, reminder);
    }
    const reminderRetry = path.match(/^\/api\/reminders\/([^/]+)\/retry$/);
    if (reminderRetry && method === "POST") {
      const reminder = state.reminders.find((item) => item.id === reminderRetry[1]);
      if (!reminder) return json(route, { error: { code: "REMINDER_NOT_FOUND" } }, 404);
      reminder.status = "pending";
      return json(route, reminder);
    }
    if (path === "/api/calendar-entries" && method === "GET") {
      return json(route, { items: state.calendars.filter((entry) => entry.status !== "cancelled"), next_cursor: null });
    }
    if (path === "/api/task-items" && method === "GET") {
      const status = url.searchParams.get("status") ?? "open";
      const dueKind = url.searchParams.get("due_kind") ?? "all";
      const items = state.tasks.filter((task) => (
        (status === "all" || task.status === status)
        && (dueKind === "all" || (dueKind === "dated") === Boolean(task.due_at))
      ));
      return json(route, { items, next_cursor: null });
    }
    const taskComplete = path.match(/^\/api\/task-items\/([^/]+)\/complete$/);
    if (taskComplete && method === "POST") {
      const index = state.tasks.findIndex((task) => task.id === taskComplete[1]);
      const current = state.tasks[index];
      if (!current || (body as Json).expected_updated_at !== current.updated_at) {
        return json(route, { error: { code: "SCHEDULE_ITEM_CONFLICT", message: "Conflict" } }, 409);
      }
      const completed = {
        ...current,
        status: "completed" as const,
        updated_at: `2026-07-21T08:00:0${sequence++}Z`,
      };
      state.tasks[index] = completed;
      return json(route, completed);
    }
    const taskReopen = path.match(/^\/api\/task-items\/([^/]+)\/reopen$/);
    if (taskReopen && method === "POST") {
      const index = state.tasks.findIndex((task) => task.id === taskReopen[1]);
      const current = state.tasks[index];
      if (!current || (body as Json).expected_updated_at !== current.updated_at) {
        return json(route, { error: { code: "SCHEDULE_ITEM_CONFLICT", message: "Conflict" } }, 409);
      }
      const reopened = {
        ...current,
        status: "open" as const,
        updated_at: `2026-07-21T08:00:0${sequence++}Z`,
      };
      state.tasks[index] = reopened;
      return json(route, reopened);
    }
    const calendarUpdate = path.match(/^\/api\/calendar-entries\/([^/]+)$/);
    if (calendarUpdate && method === "PUT") {
      const index = state.calendars.findIndex((entry) => entry.id === calendarUpdate[1]);
      const current = state.calendars[index];
      if (!current || (body as Json).expected_updated_at !== current.updated_at) {
        return json(route, { error: { code: "SCHEDULE_ITEM_CONFLICT", message: "Conflict" } }, 409);
      }
      const version = `2026-07-21T08:00:0${sequence++}Z`;
      const timingKind = (body as Json).timing_kind as "timed" | "anytime";
      const updated: CalendarEntry = {
        ...current,
        title: String((body as Json).title),
        timing_kind: timingKind,
        scheduled_date: timingKind === "anytime" ? String((body as Json).scheduled_date) : null,
        start_time: timingKind === "timed" ? String((body as Json).start_time) : null,
        end_time: timingKind === "timed" ? String((body as Json).start_time) : null,
        updated_at: version,
      };
      state.calendars[index] = updated;
      return json(route, updated);
    }
    await json(route, { error: { code: "NOT_MOCKED", message: `${method} ${path}` } }, 500);
  });

  return state;
}

export function schedulePart(entry: CalendarEntry, toolCallId: string): Json {
  return {
    tool_call_id: toolCallId,
    operation: "calendar_entry_created",
    item: { kind: "calendar", value: entry },
  };
}

export function terminalEvents(parts: Json[], content = "安排好了。") {
  return [
    ...parts.map((part) => ({ type: "schedule_item_result", data: part })),
    { type: "run_completed", data: { content, parts } },
  ];
}
