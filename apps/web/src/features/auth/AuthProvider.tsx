"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  authenticationRequiredEvent,
  userFacingApiError,
} from "@/lib/api/client";
import {
  getAccount,
  getAuthCapabilities,
  loginAccount,
  logoutAccount,
  registerAccount,
  type Account,
  type Registration,
} from "./api";

type AuthContextValue = {
  account: Account | null;
  isLoading: boolean;
  passwordResetAvailable: boolean;
  recoveryError: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  register: (registration: Registration) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [passwordResetAvailable, setPasswordResetAvailable] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);

  useEffect(() => {
    function invalidateSession() {
      localStorage.removeItem("dayboard.thread_id");
      setAccount(null);
    }
    window.addEventListener(authenticationRequiredEvent, invalidateSession);
    return () => window.removeEventListener(authenticationRequiredEvent, invalidateSession);
  }, []);

  useEffect(() => {
    void getAccount()
      .then(setAccount)
      .catch((error: unknown) => {
        setAccount(null);
        if (!(error instanceof ApiError && error.status === 401)) {
          setRecoveryError(userFacingApiError(error, "暂时无法连接服务"));
        }
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    void getAuthCapabilities()
      .then((capabilities) => setPasswordResetAvailable(capabilities.password_reset_available))
      .catch(() => setPasswordResetAvailable(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      account,
      isLoading,
      passwordResetAvailable,
      recoveryError,
      async login(identifier, password) {
        setRecoveryError(null);
        setAccount(await loginAccount(identifier, password));
      },
      async register(registration) {
        setRecoveryError(null);
        setAccount(await registerAccount(registration));
      },
      async logout() {
        await logoutAccount();
        localStorage.removeItem("dayboard.thread_id");
        setAccount(null);
      },
    }),
    [account, isLoading, passwordResetAvailable, recoveryError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
