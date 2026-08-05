"use client";

import { useSyncExternalStore } from "react";
import { Globe2, LogOut, Monitor, Moon, Settings2, Sun, UserRound, X } from "lucide-react";
import { useI18n, type Locale } from "@/i18n";
import { Button } from "@/components/ui/button";
import { timezoneDisplayName } from "./date";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import styles from "./ScheduleSettingsDrawer.module.css";

type ScheduleSettingsDrawerProps = {
  accountName: string;
  onLogout: () => void;
  timezone: string;
};

type ThemePreference = "system" | "light" | "dark";

const themeOptions: Array<{
  icon: typeof Monitor;
  value: ThemePreference;
}> = [
  { icon: Monitor, value: "system" },
  { icon: Sun, value: "light" },
  { icon: Moon, value: "dark" },
];

const themeChangeEvent = "dayboard-theme-change";
const releaseVersion = process.env.NEXT_PUBLIC_DAYBOARD_RELEASE?.trim() || "dev";

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
  const { locale, setLocale, t } = useI18n();
  const theme = useSyncExternalStore(
    subscribeToThemePreference,
    getThemePreference,
    () => "system",
  );

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button
            aria-label={t("common.settings")}
            className={styles.trigger}
            size="icon"
            title={t("common.settings")}
            type="button"
            variant="ghost"
          />
        }
      >
          <Settings2 aria-hidden="true" size={18} />
      </SheetTrigger>
      <SheetContent
        aria-describedby={undefined}
        className={styles.drawer}
        overlayClassName={styles.overlay}
        showCloseButton={false}
      >
          <header className={styles.drawerHeader}>
            <SheetTitle>{t("common.settings")}</SheetTitle>
            <SheetClose
              render={
                <Button
                  aria-label={`${t("common.close")}${t("common.settings")}`}
                  className={styles.closeButton}
                  size="icon"
                  title={t("common.close")}
                  type="button"
                  variant="ghost"
                />
              }
            >
                <X aria-hidden="true" size={20} />
            </SheetClose>
          </header>

          <div className={styles.accountSection}>
            <span aria-hidden="true" className={styles.accountIcon}>
              <UserRound size={20} />
            </span>
            <div className={styles.accountCopy}>
              <strong>{accountName}</strong>
              <span>
                <Globe2 aria-hidden="true" size={14} />
                {timezoneDisplayName(timezone, locale)}
              </span>
            </div>
          </div>

          <section className={styles.preferenceSection}>
            <span className={styles.preferenceLabel}>{t("common.appearance")}</span>
            <div aria-label={t("common.appearance")} className={styles.themeControl} role="group">
              {themeOptions.map((option) => {
                const Icon = option.icon;
                const label = option.value === "system"
                  ? t("common.system")
                  : option.value === "light" ? t("common.light") : t("common.dark");
                return (
                  <Button
                    aria-pressed={theme === option.value}
                    className={theme === option.value ? styles.themeOptionActive : styles.themeOption}
                    key={option.value}
                    onClick={() => applyThemePreference(option.value)}
                    title={label}
                    type="button"
                    variant="ghost"
                  >
                    <Icon aria-hidden="true" size={17} />
                    <span>{label}</span>
                  </Button>
                );
              })}
            </div>
          </section>

          <section className={styles.preferenceSection}>
            <label className={styles.preferenceLabel} htmlFor="dayboard-language">
              {t("common.language")}
            </label>
            <select
              className={styles.languageSelect}
              id="dayboard-language"
              value={locale}
              onChange={(event) => setLocale(event.target.value as Locale)}
            >
              <option value="zh-CN">{t("common.chinese")}</option>
              <option value="en-US">{t("common.english")}</option>
            </select>
          </section>

          <div className={styles.drawerActions}>
            <div className={styles.releaseInfo}>
              <span>{t("common.version")}</span>
              <code>{releaseVersion}</code>
            </div>
            <Button className={styles.logoutButton} onClick={onLogout} type="button" variant="destructive">
              <LogOut aria-hidden="true" size={18} />
              {t("common.logout")}
            </Button>
          </div>
      </SheetContent>
    </Sheet>
  );
}
