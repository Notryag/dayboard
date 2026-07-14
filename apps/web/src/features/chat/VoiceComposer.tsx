"use client";

import { useEffect, useRef, useState } from "react";
import { Keyboard, LoaderCircle, X } from "lucide-react";
import styles from "./Composer.module.css";

export type VoiceComposerStatus = "idle" | "requesting" | "recording" | "transcribing";

type ReleaseAction = "stop" | "cancel";

type VoiceComposerProps = {
  disabled: boolean;
  elapsedSeconds: number;
  level: number;
  maxDurationSeconds: number;
  onCancelRecording: () => void;
  onCancelTranscription: () => void;
  onStartRecording: () => Promise<void>;
  onStopRecording: () => void;
  onSwitchToText: () => void;
  status: VoiceComposerStatus;
  unavailableReason: string | null;
};

const CANCEL_DISTANCE_PX = 64;
const LEVEL_WEIGHTS = [0.48, 0.76, 1, 0.68, 0.42];

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

export function VoiceComposer({
  disabled,
  elapsedSeconds,
  level,
  maxDurationSeconds,
  onCancelRecording,
  onCancelTranscription,
  onStartRecording,
  onStopRecording,
  onSwitchToText,
  status,
  unavailableReason,
}: VoiceComposerProps) {
  const [cancelIntent, setCancelIntent] = useState(false);
  const activeRef = useRef(false);
  const cancelIntentRef = useRef(false);
  const pointerIdRef = useRef<number | null>(null);
  const previousStatusRef = useRef(status);
  const startResolvedRef = useRef(false);
  const startYRef = useRef(0);
  const pendingReleaseRef = useRef<ReleaseAction | null>(null);

  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    previousStatusRef.current = status;
    if (status !== "transcribing" && !(status === "idle" && previousStatus !== "idle")) {
      return;
    }

    activeRef.current = false;
    cancelIntentRef.current = false;
    pendingReleaseRef.current = null;
    pointerIdRef.current = null;
    startResolvedRef.current = false;
    setCancelIntent(false);
  }, [status]);

  function performRelease(action: ReleaseAction) {
    pendingReleaseRef.current = null;
    activeRef.current = false;
    startResolvedRef.current = false;
    cancelIntentRef.current = false;
    setCancelIntent(false);
    if (action === "cancel") onCancelRecording();
    else onStopRecording();
  }

  async function beginRecording() {
    if (disabled || status !== "idle" || activeRef.current) return;
    activeRef.current = true;
    startResolvedRef.current = false;
    pendingReleaseRef.current = null;
    cancelIntentRef.current = false;
    setCancelIntent(false);
    await onStartRecording();
    startResolvedRef.current = true;
    if (!activeRef.current && pendingReleaseRef.current) {
      performRelease(pendingReleaseRef.current);
    }
  }

  function finishRecording(action: ReleaseAction) {
    if (!activeRef.current) return;
    activeRef.current = false;
    const resolvedAction = cancelIntentRef.current ? "cancel" : action;
    if (startResolvedRef.current) performRelease(resolvedAction);
    else pendingReleaseRef.current = "cancel";
  }

  const primaryLabel = unavailableReason ?? "按住说话";
  const elapsedLabel = formatDuration(elapsedSeconds);
  const visualLabel =
    status === "requesting"
      ? "正在连接"
      : status === "recording"
        ? cancelIntent
          ? "松开取消"
          : "松开发送"
        : status === "transcribing"
          ? "正在识别"
          : primaryLabel;
  const controlLabel =
    status === "requesting"
      ? "正在连接麦克风"
      : status === "recording"
        ? cancelIntent
          ? "松开取消"
          : `松开发送，已录音 ${elapsedLabel}，最长 ${formatDuration(maxDurationSeconds)}`
        : status === "transcribing"
          ? "正在识别语音"
          : primaryLabel;

  return (
    <div className={`${styles.composer} ${styles.voiceComposer}`}>
      <span aria-live="polite" className={styles.srOnly}>
        {controlLabel}
      </span>

      <button
        aria-label={controlLabel}
        aria-pressed={status === "requesting" || status === "recording"}
        className={`${styles.voiceHoldButton} ${
          status === "recording" ? styles.voiceHoldButtonActive : ""
        } ${
          status === "requesting" || status === "transcribing"
            ? styles.voiceHoldButtonProcessing
            : ""
        } ${cancelIntent ? styles.voiceHoldButtonCancel : ""}`}
        disabled={(status === "idle" && disabled) || status === "transcribing"}
        onBlur={() => finishRecording("cancel")}
        onContextMenu={(event) => event.preventDefault()}
        onKeyDown={(event) => {
          if ((event.key === " " || event.key === "Enter") && !event.repeat) {
            event.preventDefault();
            void beginRecording();
          }
        }}
        onKeyUp={(event) => {
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            finishRecording("stop");
          }
        }}
        onPointerDown={(event) => {
          if (event.button !== 0 || disabled || status !== "idle") return;
          event.preventDefault();
          pointerIdRef.current = event.pointerId;
          startYRef.current = event.clientY;
          event.currentTarget.setPointerCapture(event.pointerId);
          void beginRecording();
        }}
        onPointerMove={(event) => {
          if (pointerIdRef.current !== event.pointerId || !activeRef.current) return;
          const nextIntent = startYRef.current - event.clientY >= CANCEL_DISTANCE_PX;
          if (cancelIntentRef.current !== nextIntent) {
            cancelIntentRef.current = nextIntent;
            setCancelIntent(nextIntent);
          }
        }}
        onPointerUp={(event) => {
          if (pointerIdRef.current !== event.pointerId) return;
          pointerIdRef.current = null;
          finishRecording("stop");
        }}
        onPointerCancel={(event) => {
          if (pointerIdRef.current !== event.pointerId) return;
          pointerIdRef.current = null;
          finishRecording("cancel");
        }}
        title={status === "idle" ? primaryLabel : undefined}
        type="button"
      >
        {status === "recording" ? (
          <span className={styles.voiceButtonFeedback}>
            <span className={styles.levelBars} aria-hidden="true">
              {LEVEL_WEIGHTS.map((weight, index) => (
                <span
                  key={index}
                  style={{ transform: `scaleY(${Math.max(0.2, level * weight)})` }}
                />
              ))}
            </span>
            <span className={styles.voiceButtonLabel}>{visualLabel}</span>
            <span className={styles.durationLimit}>{elapsedLabel}</span>
          </span>
        ) : status === "requesting" || status === "transcribing" ? (
          <span className={styles.voiceButtonState}>
            <LoaderCircle className={styles.spinner} size={18} />
            <span className={styles.voiceButtonLabel}>{visualLabel}</span>
          </span>
        ) : (
          <span className={styles.voiceButtonLabel}>{visualLabel}</span>
        )}
      </button>

      {status === "idle" ? (
        <button
          aria-label="切换到键盘输入"
          className={styles.iconButton}
          onClick={onSwitchToText}
          title="键盘输入"
          type="button"
        >
          <Keyboard size={20} strokeWidth={2.1} />
        </button>
      ) : status === "transcribing" ? (
        <button
          aria-label="取消识别"
          className={styles.iconButton}
          onClick={onCancelTranscription}
          type="button"
        >
          <X size={20} />
        </button>
      ) : (
        <span aria-hidden="true" className={styles.voiceActionSpacer} />
      )}
    </div>
  );
}
