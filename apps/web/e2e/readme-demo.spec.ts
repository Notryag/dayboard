import { expect, test } from "@playwright/test";
import {
  calendarEntry,
  installApiFixture,
  schedulePart,
  terminalEvents,
} from "./api-fixture";

const recordDemo = process.env.RECORD_README_DEMO === "1";

test.skip(!recordDemo, "README demo recording is opt-in");
test.use({
  video: { mode: "on", size: { width: 390, height: 844 } },
  viewport: { width: 390, height: 844 },
});

test("record calendar creation and rescheduling for the README", async ({ page }) => {
  const original = calendarEntry({
    id: "calendar-readme-demo",
    title: "和张总开会",
    start_time: "2026-08-07T15:00:00+08:00",
    end_time: "2026-08-07T17:00:00+08:00",
  });
  const rescheduled = {
    ...original,
    row_version: 2,
    start_time: "2026-08-07T16:00:00+08:00",
    end_time: "2026-08-07T18:00:00+08:00",
    updated_at: "2026-07-27T02:00:00Z",
  };
  const state = await installApiFixture(page);

  state.onCommand = (message, fixture) => {
    if (message.includes("改到四点")) {
      fixture.calendars[0] = rescheduled;
      const part = {
        ...schedulePart(rescheduled, "tool-reschedule"),
        operation: "calendar_entry_rescheduled",
      };
      return {
        delayMs: 1100,
        events: terminalEvents([part], "已将会议改到 16:00–18:00。"),
        parts: [part],
        persistedText: "已将会议改到 16:00–18:00。",
      };
    }

    fixture.calendars.push(original);
    const part = schedulePart(original, "tool-create");
    return {
      delayMs: 1100,
      events: terminalEvents([part], "已创建 15:00–17:00 的日程。"),
      parts: [part],
      persistedText: "已创建 15:00–17:00 的日程。",
    };
  };

  await page.goto("/dayboard");
  await expect(page.getByRole("region", { name: "对话", exact: true })).toBeVisible();
  await page.waitForTimeout(2200);

  await page.getByRole("button", { name: "切换到键盘输入" }).click();
  const input = page.getByPlaceholder("输入日程或任务");
  await input.pressSequentially("下周五下午三点和张总开会，两个小时", { delay: 85 });
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("已创建 15:00–17:00 的日程。")).toBeVisible();
  await page.waitForTimeout(3600);

  await input.pressSequentially("把刚才的会议改到四点", { delay: 105 });
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("已将会议改到 16:00–18:00。")).toBeVisible();
  await page.waitForTimeout(3800);

  await page.getByRole("button", { name: "打开日程" }).click();
  await page.getByLabel("跳转日期").fill("2026-08-07");
  await expect(page.getByRole("heading", { name: "星期五" })).toBeVisible();
  await expect(page.getByRole("button", { name: "查看日程：和张总开会" })).toBeVisible();
  await page.waitForTimeout(4200);
});
