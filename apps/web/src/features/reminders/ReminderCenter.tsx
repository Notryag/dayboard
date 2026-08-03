"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing, CalendarClock, LoaderCircle, RefreshCw, RotateCw, X } from "lucide-react";
import { useI18n } from "@/i18n";
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

function reminderTitle(reminder: ReminderInboxItem, fallback: string) {
  return reminder.source_title ?? payloadString(reminder, "title") ?? fallback;
}

function reminderDate(reminder: ReminderInboxItem, timezone: string, locale: "zh-CN" | "en-US") {
  return new Intl.DateTimeFormat(locale, {
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

function statusLabel(reminder: ReminderInboxItem, t: (key: string) => string) {
  const sourceName = reminder.source_type === "task_item" ? t("reminders.task") : t("reminders.schedule");
  if (reminder.source_status === "deleted") return `${sourceName} ${t("reminders.deleted")}`;
  if (reminder.source_status === "cancelled") return `${sourceName} ${t("reminders.cancelled")}`;
  if (reminder.source_status === "completed") return `${sourceName} ${t("reminders.completed")}`;
  if (reminder.status === "failed") return t("reminders.deliveryFailed");
  return reminder.read_at ? t("reminders.read") : t("reminders.new");
}

export function ReminderCenter({ onOpenSource, timezone }: ReminderCenterProps) {
  const { locale, t } = useI18n();
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
      const notification = new Notification(reminderTitle(reminder, t("reminders.scheduleReminder")), {
        body: reminderDate(reminder, timezone, locale),
        tag: `dayboard-reminder-${reminder.id}`,
      });
      notification.onclick = () => {
        window.focus();
        notification.close();
        void openSource(reminder);
      };
    }
  }, [locale, openSource, permission, t, timezone, visible]);

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
            aria-label={unreadCount ? `${t("reminders.title")}, ${t("reminders.unread", { count: unreadCount })}` : t("reminders.title")}
            className={styles.trigger}
            size="icon"
            title={t("reminders.title")}
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
            <SheetTitle>{t("reminders.title")}</SheetTitle>
            <span>{unreadCount ? t("reminders.unread", { count: unreadCount }) : t("reminders.noUnread")}</span>
          </div>
          <div className={styles.headerActions}>
            <Button
              aria-label={t("reminders.refresh")}
              disabled={reminders.isFetching}
              onClick={() => void reminders.refetch()}
              size="icon"
              title={t("common.retry")}
              type="button"
              variant="ghost"
            >
              <RefreshCw className={reminders.isFetching ? styles.spinner : undefined} size={18} />
            </Button>
            <SheetClose
              render={
                <Button aria-label={`${t("common.close")}${t("reminders.title")}`} size="icon" title={t("common.close")} type="button" variant="ghost" />
              }
            >
              <X aria-hidden="true" size={20} />
            </SheetClose>
          </div>
        </header>

        {mutationError ? (
          <p className={styles.error} role="alert">
            {userFacingApiError(mutationError, t("reminders.operationFailed"), locale)}
          </p>
        ) : null}

        <div className={styles.content}>
          {permission !== "unsupported" ? (
            <div className={styles.notificationControl}>
              <BellRing aria-hidden="true" size={17} />
              <span>{t("reminders.notification")}</span>
              {permission === "granted" ? (
                <small>{t("reminders.enabled")}</small>
              ) : permission === "denied" ? (
                <small>{t("reminders.blocked")}</small>
              ) : (
                <Button onClick={() => void requestNotificationPermission()} size="sm" type="button" variant="outline">
                  {t("reminders.enable")}
                </Button>
              )}
            </div>
          ) : null}
          {reminders.isPending ? (
            <div className={styles.notice} role="status">
              <LoaderCircle className={styles.spinner} size={20} />
              {t("reminders.loading")}
            </div>
          ) : reminders.error ? (
            <div className={styles.notice} role="alert">
              <span>{userFacingApiError(reminders.error, t("reminders.loadFailed"), locale)}</span>
              <Button onClick={() => void reminders.refetch()} size="sm" type="button" variant="outline">
                {t("common.retry")}
              </Button>
            </div>
          ) : !visible.length ? (
            <div className={styles.empty}>
              <Bell aria-hidden="true" size={22} />
              <p>{t("reminders.empty")}</p>
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
                        <strong>{reminderTitle(reminder, t("reminders.scheduleReminder"))}</strong>
                        <span>{reminderDate(reminder, timezone, locale)}</span>
                        <small data-source-status={reminder.source_status} data-status={reminder.status}>
                          {statusLabel(reminder, t)}
                        </small>
                      </span>
                    </button>
                    {reminder.status === "failed" && reminder.can_retry ? (
                      <Button
                        aria-label={`${t("reminders.redeliver")}: ${reminderTitle(reminder, t("reminders.scheduleReminder"))}`}
                        disabled={retry.isPending && retry.variables === reminder.id}
                        onClick={() => retry.mutate(reminder.id)}
                        size="icon"
                        title={t("reminders.redeliver")}
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
