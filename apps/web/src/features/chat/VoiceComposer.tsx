"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Keyboard, LoaderCircle, X } from "lucide-react";
import { useI18n } from "@/i18n";
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

const CANCEL_TARGET_EXIT_PADDING_PX = 14;
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
  const { t } = useI18n();
  const [cancelIntent, setCancelIntent] = useState(false);
  const activeRef = useRef(false);
  const cancelIntentRef = useRef(false);
  const cancelTargetRef = useRef<HTMLDivElement>(null);
  const lastPointerPositionRef = useRef<{ x: number; y: number } | null>(null);
  const pointerCleanupRef = useRef<(() => void) | null>(null);
  const pointerIdRef = useRef<number | null>(null);
  const previousStatusRef = useRef(status);
  const startResolvedRef = useRef(false);

  const isInsideCancelTarget = useCallback((clientX: number, clientY: number) => {
    const bounds = cancelTargetRef.current?.getBoundingClientRect();
    if (!bounds) return false;
    const padding = cancelIntentRef.current ? CANCEL_TARGET_EXIT_PADDING_PX : 0;
    return (
      clientX >= bounds.left - padding &&
      clientX <= bounds.right + padding &&
      clientY >= bounds.top - padding &&
      clientY <= bounds.bottom + padding
    );
  }, []);

  const updateCancelIntent = useCallback((clientX: number, clientY: number) => {
    lastPointerPositionRef.current = { x: clientX, y: clientY };
    const nextIntent = isInsideCancelTarget(clientX, clientY);
    if (cancelIntentRef.current === nextIntent) return;
    cancelIntentRef.current = nextIntent;
    setCancelIntent(nextIntent);
  }, [isInsideCancelTarget]);

  useEffect(() => {
    if (status !== "requesting" && status !== "recording") return;
    const position = lastPointerPositionRef.current;
    if (!position) return;
    const frame = window.requestAnimationFrame(() => {
      updateCancelIntent(position.x, position.y);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [status, updateCancelIntent]);

  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    previousStatusRef.current = status;
    if (status !== "transcribing" && !(status === "idle" && previousStatus !== "idle")) {
      return;
    }

    activeRef.current = false;
    cancelIntentRef.current = false;
    pointerCleanupRef.current?.();
    pointerCleanupRef.current = null;
    pointerIdRef.current = null;
    lastPointerPositionRef.current = null;
    startResolvedRef.current = false;
    setCancelIntent(false);
  }, [status]);

  useEffect(() => () => pointerCleanupRef.current?.(), []);

  function stopPointerTracking() {
    pointerCleanupRef.current?.();
    pointerCleanupRef.current = null;
  }

  function performRelease(action: ReleaseAction) {
    stopPointerTracking();
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
    cancelIntentRef.current = false;
    setCancelIntent(false);
    await onStartRecording();
    startResolvedRef.current = true;
  }

  function finishRecording(action: ReleaseAction) {
    if (!activeRef.current) return;
    activeRef.current = false;
    const resolvedAction = cancelIntentRef.current ? "cancel" : action;
    if (startResolvedRef.current) performRelease(resolvedAction);
    else {
      cancelIntentRef.current = false;
      setCancelIntent(false);
      onCancelRecording();
    }
  }

  function beginPointerTracking() {
    stopPointerTracking();
    const handleMove = (event: PointerEvent) => {
      if (pointerIdRef.current !== event.pointerId || !activeRef.current) return;
      event.preventDefault();
      const samples = event.getCoalescedEvents?.();
      const latest = samples?.[samples.length - 1] ?? event;
      updateCancelIntent(latest.clientX, latest.clientY);
    };
    const handleUp = (event: PointerEvent) => {
      if (pointerIdRef.current !== event.pointerId) return;
      updateCancelIntent(event.clientX, event.clientY);
      pointerIdRef.current = null;
      stopPointerTracking();
      finishRecording("stop");
    };
    const handleCancel = (event: PointerEvent) => {
      if (pointerIdRef.current !== event.pointerId) return;
      pointerIdRef.current = null;
      stopPointerTracking();
      finishRecording("cancel");
    };
    window.addEventListener("pointermove", handleMove, { passive: false });
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleCancel);
    pointerCleanupRef.current = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleCancel);
    };
  }

  const primaryLabel = unavailableReason ?? t("voice.holdToTalk");
  const elapsedLabel = formatDuration(elapsedSeconds);
  const visualLabel =
    status === "requesting"
      ? t("voice.connecting")
      : status === "recording"
        ? cancelIntent
          ? t("voice.releaseToCancel")
          : t("voice.releaseToSend")
        : status === "transcribing"
          ? t("voice.transcribing")
          : primaryLabel;
  const controlLabel =
    status === "requesting"
      ? t("voice.connectingMicrophone")
      : status === "recording"
        ? cancelIntent
          ? t("voice.releaseToCancel")
          : t("voice.recordingInfo", { elapsed: elapsedLabel, max: formatDuration(maxDurationSeconds) })
        : status === "transcribing"
          ? t("voice.transcribingVoice")
          : primaryLabel;

  return (
    <div className={`${styles.composer} ${styles.voiceComposer}`}>
      <span aria-live="polite" className={styles.srOnly}>
        {controlLabel}
      </span>

      {status === "requesting" || status === "recording" ? (
        <div
          aria-hidden="true"
          className={`${styles.voiceCancelTarget} ${
            cancelIntent ? styles.voiceCancelTargetActive : ""
          }`}
          ref={cancelTargetRef}
        >
          <span className={styles.voiceCancelIcon}>
            <X size={18} strokeWidth={2.4} />
          </span>
          <span>{cancelIntent ? t("voice.releaseToCancel") : t("voice.moveHereToCancel")}</span>
        </div>
      ) : null}

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
        onBlur={() => {
          stopPointerTracking();
          finishRecording("cancel");
        }}
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
          lastPointerPositionRef.current = { x: event.clientX, y: event.clientY };
          beginPointerTracking();
          try {
            event.currentTarget.setPointerCapture(event.pointerId);
          } catch {
            // Window-level tracking covers embedded browsers that reject pointer capture.
          }
          void beginRecording();
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
          aria-label={t("chat.switchToKeyboard")}
          className={styles.iconButton}
          onClick={onSwitchToText}
          title={t("chat.keyboardInput")}
          type="button"
        >
          <Keyboard size={20} strokeWidth={2.1} />
        </button>
      ) : status === "transcribing" ? (
        <button
          aria-label={t("common.cancel")}
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
