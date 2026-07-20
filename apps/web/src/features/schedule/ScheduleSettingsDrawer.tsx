"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useSyncExternalStore } from "react";
import { Globe2, LogOut, Monitor, Moon, Settings2, Sun, UserRound, X } from "lucide-react";
import styles from "./ScheduleSettingsDrawer.module.css";

type ScheduleSettingsDrawerProps = {
  accountName: string;
  onLogout: () => void;
  timezone: string;
};

type ThemePreference = "system" | "light" | "dark";

const themeOptions: Array<{
  icon: typeof Monitor;
  label: string;
  value: ThemePreference;
}> = [
  { icon: Monitor, label: "跟随系统", value: "system" },
  { icon: Sun, label: "浅色", value: "light" },
  { icon: Moon, label: "深色", value: "dark" },
];

const themeChangeEvent = "dayboard-theme-change";

function getThemePreference(): ThemePreference {
  const storedTheme = localStorage.getItem("dayboard-theme");
  return storedTheme === "light" || storedTheme === "dark" ? storedTheme : "system";
}

function subscribeToThemePreference(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(themeChangeEvent, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(themeChangeEvent, onStoreChange);
  };
}

function applyThemePreference(theme: ThemePreference) {
  if (theme === "system") {
    localStorage.removeItem("dayboard-theme");
    document.documentElement.removeAttribute("data-theme");
  } else {
    localStorage.setItem("dayboard-theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }
  window.dispatchEvent(new Event(themeChangeEvent));
}

export function ScheduleSettingsDrawer({
  accountName,
  onLogout,
  timezone,
}: ScheduleSettingsDrawerProps) {
  const theme = useSyncExternalStore(
    subscribeToThemePreference,
    getThemePreference,
    () => "system",
  );

  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button aria-label="打开设置" className={styles.trigger} title="设置" type="button">
          <Settings2 aria-hidden="true" size={18} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content aria-describedby={undefined} className={styles.drawer}>
          <header className={styles.drawerHeader}>
            <Dialog.Title>设置</Dialog.Title>
            <Dialog.Close asChild>
              <button aria-label="关闭设置" className={styles.closeButton} title="关闭" type="button">
                <X aria-hidden="true" size={20} />
              </button>
            </Dialog.Close>
          </header>

          <div className={styles.accountSection}>
            <span aria-hidden="true" className={styles.accountIcon}>
              <UserRound size={20} />
            </span>
            <div className={styles.accountCopy}>
              <strong>{accountName}</strong>
              <span>
                <Globe2 aria-hidden="true" size={14} />
                {timezone}
              </span>
            </div>
          </div>

          <section className={styles.preferenceSection}>
            <span className={styles.preferenceLabel}>外观</span>
            <div aria-label="外观主题" className={styles.themeControl} role="group">
              {themeOptions.map((option) => {
                const Icon = option.icon;
                return (
                  <button
                    aria-pressed={theme === option.value}
                    className={theme === option.value ? styles.themeOptionActive : styles.themeOption}
                    key={option.value}
                    onClick={() => applyThemePreference(option.value)}
                    title={option.label}
                    type="button"
                  >
                    <Icon aria-hidden="true" size={17} />
                    <span>{option.label}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <div className={styles.drawerActions}>
            <button className={styles.logoutButton} onClick={onLogout} type="button">
              <LogOut aria-hidden="true" size={18} />
              退出登录
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
