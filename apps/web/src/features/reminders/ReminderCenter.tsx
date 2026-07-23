"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing, CalendarClock, LoaderCircle, RefreshCw, RotateCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { userFacingApiError } from "@/lib/api/client";
import type { ReminderInboxItem } from "@/lib/api/types";
import { getReminders, markReminderRead, retryReminder } from "./api";
import type { ReminderFocusTarget } from "./types";
import styles from "./ReminderCenter.module.css";

type ReminderCenterProps = {
  onOpenSource: (target: Omit<ReminderFocusTarget, "requestId">) => void;
  timezone: string;
};

type NotificationPermissionState = NotificationPermission | "unsupported";
const notificationPermissionEvent = "dayboard:notification-permission";

function notificationPermission(): NotificationPermissionState {
  return typeof Notification === "undefined" ? "unsupported" : Notification.permission;
}

function subscribeNotificationPermission(onChange: () => void) {
  window.addEventListener(notificationPermissionEvent, onChange);
  return () => window.removeEventListener(notificationPermissionEvent, onChange);
}

function payloadString(reminder: ReminderInboxItem, key: string) {
  const value = reminder.payload[key];
  return typeof value === "string" ? value : null;
}

function reminderTitle(reminder: ReminderInboxItem) {
  return payloadString(reminder, "title") ?? "日程提醒";
}

function reminderDate(reminder: ReminderInboxItem, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone,
  }).format(new Date(reminder.source_occurs_at));
}

function dateKey(reminder: ReminderInboxItem, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: timezone,
  }).formatToParts(new Date(reminder.source_occurs_at));
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function sourceUnavailable(reminder: ReminderInboxItem) {
  return reminder.source_status === "deleted" || reminder.source_status === "cancelled";
}

function statusLabel(reminder: ReminderInboxItem) {
  if (sourceUnavailable(reminder)) return reminder.source_type === "task_item" ? "待办已删除" : "日程已删除";
  if (reminder.status === "failed") return "投递失败";
  return reminder.read_at ? "已读" : "新提醒";
}

export function ReminderCenter({ onOpenSource, timezone }: ReminderCenterProps) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const permission = useSyncExternalStore(
    subscribeNotificationPermission,
    notificationPermission,
    () => "unsupported",
  );
  const reminders = useQuery({
    queryKey: ["reminders"],
    queryFn: getReminders,
    refetchInterval: 15_000,
  });
  const visible = useMemo(() => reminders.data ?? [], [reminders.data]);
  const unreadCount = visible.filter(
    (item) => item.status === "delivered" && item.read_at === null && !sourceUnavailable(item),
  ).length;

  const markRead = useMutation({
    mutationFn: markReminderRead,
    onSuccess: (updated) => {
      void updated;
      void queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
  const retry = useMutation({
    mutationFn: retryReminder,
    onSuccess: (updated) => {
      queryClient.setQueryData<ReminderInboxItem[]>(["reminders"], (current = []) =>
        current.filter((item) => item.id !== updated.id));
      void queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
  });

  const openSource = useCallback(async (reminder: ReminderInboxItem) => {
    if (sourceUnavailable(reminder)) return;
    if (reminder.status === "delivered" && !reminder.read_at) {
      await markRead.mutateAsync(reminder.id).catch(() => undefined);
    }
    setOpen(false);
    onOpenSource({
      date: dateKey(reminder, timezone),
      sourceId: reminder.source_id,
      sourceType: reminder.source_type,
    });
  }, [markRead, onOpenSource, timezone]);

  const mutationError = markRead.error ?? retry.error;

  useEffect(() => {
    if (permission !== "granted") return;
    for (const reminder of visible) {
      if (reminder.status !== "delivered" || reminder.read_at || sourceUnavailable(reminder)) continue;
      const storageKey = `dayboard:notification:${reminder.id}`;
      if (sessionStorage.getItem(storageKey)) continue;
      sessionStorage.setItem(storageKey, "shown");
      const notification = new Notification(reminderTitle(reminder), {
        body: reminderDate(reminder, timezone),
        tag: `dayboard-reminder-${reminder.id}`,
      });
      notification.onclick = () => {
        window.focus();
        notification.close();
        void openSource(reminder);
      };
    }
  }, [openSource, permission, timezone, visible]);

  async function requestNotificationPermission() {
    if (typeof Notification === "undefined") return;
    await Notification.requestPermission();
    window.dispatchEvent(new Event(notificationPermissionEvent));
  }

  return (
    <Sheet onOpenChange={setOpen} open={open}>
      <SheetTrigger
        render={
          <Button
            aria-label={unreadCount ? `提醒，${unreadCount} 条未读` : "提醒"}
            className={styles.trigger}
            size="icon"
            title="提醒"
            type="button"
            variant="ghost"
          />
        }
      >
        <Bell aria-hidden="true" size={18} />
        {unreadCount ? <span className={styles.badge}>{unreadCount > 9 ? "9+" : unreadCount}</span> : null}
      </SheetTrigger>
      <SheetContent
        aria-describedby={undefined}
        className={styles.drawer}
        overlayClassName={styles.overlay}
        showCloseButton={false}
      >
        <header className={styles.header}>
          <div>
            <SheetTitle>提醒</SheetTitle>
            <span>{unreadCount ? `${unreadCount} 条未读` : "没有未读提醒"}</span>
          </div>
          <div className={styles.headerActions}>
            <Button
              aria-label="刷新提醒"
              disabled={reminders.isFetching}
              onClick={() => void reminders.refetch()}
              size="icon"
              title="刷新"
              type="button"
              variant="ghost"
            >
              <RefreshCw className={reminders.isFetching ? styles.spinner : undefined} size={18} />
            </Button>
            <SheetClose
              render={
                <Button aria-label="关闭提醒" size="icon" title="关闭" type="button" variant="ghost" />
              }
            >
              <X aria-hidden="true" size={20} />
            </SheetClose>
          </div>
        </header>

        {mutationError ? (
          <p className={styles.error} role="alert">
            {userFacingApiError(mutationError, "提醒操作失败，请稍后重试。")}
          </p>
        ) : null}

        <div className={styles.content}>
          {permission !== "unsupported" ? (
            <div className={styles.notificationControl}>
              <BellRing aria-hidden="true" size={17} />
              <span>浏览器通知</span>
              {permission === "granted" ? (
                <small>已开启</small>
              ) : permission === "denied" ? (
                <small>已被浏览器阻止</small>
              ) : (
                <Button onClick={() => void requestNotificationPermission()} size="sm" type="button" variant="outline">
                  开启
                </Button>
              )}
            </div>
          ) : null}
          {reminders.isPending ? (
            <div className={styles.notice} role="status">
              <LoaderCircle className={styles.spinner} size={20} />
              正在加载提醒
            </div>
          ) : reminders.error ? (
            <div className={styles.notice} role="alert">
              <span>{userFacingApiError(reminders.error, "暂时无法加载提醒。")}</span>
              <Button onClick={() => void reminders.refetch()} size="sm" type="button" variant="outline">
                重试
              </Button>
            </div>
          ) : !visible.length ? (
            <div className={styles.empty}>
              <Bell aria-hidden="true" size={22} />
              <p>还没有提醒</p>
            </div>
          ) : (
            <ol className={styles.list}>
              {visible.map((reminder) => {
                const unavailable = sourceUnavailable(reminder);
                const unread = reminder.status === "delivered" && !reminder.read_at && !unavailable;
                return (
                  <li className={`${styles.item} ${unread ? styles.unread : ""}`} key={reminder.id}>
                    <button
                      className={styles.itemMain}
                      disabled={unavailable}
                      onClick={() => void openSource(reminder)}
                      type="button"
                    >
                      <span className={styles.itemIcon}><CalendarClock size={17} /></span>
                      <span className={styles.itemCopy}>
                        <strong>{reminderTitle(reminder)}</strong>
                        <span>{reminderDate(reminder, timezone)}</span>
                        <small data-source-status={reminder.source_status} data-status={reminder.status}>
                          {statusLabel(reminder)}
                        </small>
                      </span>
                    </button>
                    {reminder.status === "failed" ? (
                      <Button
                        aria-label={`重新投递：${reminderTitle(reminder)}`}
                        disabled={retry.isPending && retry.variables === reminder.id}
                        onClick={() => retry.mutate(reminder.id)}
                        size="icon"
                        title="重新投递"
                        type="button"
                        variant="ghost"
                      >
                        {retry.isPending && retry.variables === reminder.id
                          ? <LoaderCircle className={styles.spinner} size={16} />
                          : <RotateCw size={16} />}
                      </Button>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
