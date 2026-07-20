"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Globe2, LogOut, Settings2, UserRound, X } from "lucide-react";
import styles from "./ScheduleSettingsDrawer.module.css";

type ScheduleSettingsDrawerProps = {
  accountName: string;
  onLogout: () => void;
  timezone: string;
};

export function ScheduleSettingsDrawer({
  accountName,
  onLogout,
  timezone,
}: ScheduleSettingsDrawerProps) {
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
