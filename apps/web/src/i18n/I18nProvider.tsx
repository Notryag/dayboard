"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { getMessage, type Locale, type MessageValues } from "./messages";

const STORAGE_KEY = "dayboard-locale";
const localeListeners = new Set<() => void>();

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: MessageValues) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value === "zh-CN" || value === "en-US";
}

function browserLocale(): Locale {
  return typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("en")
    ? "en-US"
    : "zh-CN";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(
    (onStoreChange) => {
      localeListeners.add(onStoreChange);
      window.addEventListener("storage", onStoreChange);
      return () => {
        localeListeners.delete(onStoreChange);
        window.removeEventListener("storage", onStoreChange);
      };
    },
    () => {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      return isLocale(stored) ? stored : browserLocale();
    },
    (): Locale => "zh-CN",
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    window.localStorage.setItem(STORAGE_KEY, nextLocale);
    localeListeners.forEach((listener) => listener());
  }, []);

  const t = useCallback(
    (key: string, values?: MessageValues) => getMessage(locale, key, values),
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within I18nProvider");
  return context;
}
