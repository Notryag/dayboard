"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, userFacingApiError } from "@/lib/api/client";
import {
  getAccount,
  loginAccount,
  logoutAccount,
  registerAccount,
  type Account,
  type Registration,
} from "./api";

type AuthContextValue = {
  account: Account | null;
  isLoading: boolean;
  recoveryError: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  register: (registration: Registration) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);

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

  const value = useMemo<AuthContextValue>(
    () => ({
      account,
      isLoading,
      recoveryError,
      async login(identifier, password) {
        setAccount(await loginAccount(identifier, password));
      },
      async register(registration) {
        setAccount(await registerAccount(registration));
      },
      async logout() {
        await logoutAccount();
        localStorage.removeItem("dayboard.thread_id");
        setAccount(null);
      },
    }),
    [account, isLoading, recoveryError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
