"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
  const queryClient = useQueryClient();
  const [account, setAccount] = useState<Account | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [passwordResetAvailable, setPasswordResetAvailable] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);

  useEffect(() => {
    function invalidateSession() {
      localStorage.removeItem("dayboard.thread_id");
      queryClient.clear();
      setAccount(null);
    }
    window.addEventListener(authenticationRequiredEvent, invalidateSession);
    return () => window.removeEventListener(authenticationRequiredEvent, invalidateSession);
  }, [queryClient]);

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
        const nextAccount = await loginAccount(identifier, password);
        queryClient.clear();
        setAccount(nextAccount);
      },
      async register(registration) {
        setRecoveryError(null);
        const nextAccount = await registerAccount(registration);
        queryClient.clear();
        setAccount(nextAccount);
      },
      async logout() {
        await logoutAccount();
        localStorage.removeItem("dayboard.thread_id");
        queryClient.clear();
        setAccount(null);
      },
    }),
    [account, isLoading, passwordResetAvailable, queryClient, recoveryError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
