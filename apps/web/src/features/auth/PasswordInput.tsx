"use client";

import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import styles from "./PasswordInput.module.css";

type PasswordInputProps = {
  autoComplete: "current-password" | "new-password";
  label: string;
  minLength: number;
  name: string;
};

export function PasswordInput({ autoComplete, label, minLength, name }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const inputId = useId();

  return (
    <div className={styles.group}>
      <label htmlFor={inputId}>{label}</label>
      <span className={styles.field}>
        <input
          autoComplete={autoComplete}
          id={inputId}
          minLength={minLength}
          name={name}
          required
          type={visible ? "text" : "password"}
        />
        <button
          aria-label={visible ? `隐藏${label}` : `显示${label}`}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
          title={visible ? "隐藏密码" : "显示密码"}
          type="button"
        >
          {visible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}
        </button>
      </span>
    </div>
  );
}
