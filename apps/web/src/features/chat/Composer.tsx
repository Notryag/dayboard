"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, X } from "lucide-react";
import { useI18n } from "@/i18n";
import { userFacingApiError } from "@/lib/api/client";
import {
  getVoiceCapabilities,
  reportVoiceStartupMetric,
  transcribeVoice,
} from "@/features/voice/api";
import type {
  RecordedAudio,
  VoiceCapabilities,
  VoiceStartupMetric,
} from "@/features/voice/types";
import { useVoiceRecorder } from "@/features/voice/useVoiceRecorder";
import { TextComposer } from "./TextComposer";
import { VoiceComposer, type VoiceComposerStatus } from "./VoiceComposer";
import styles from "./Composer.module.css";

type ComposerProps = {
  activeRunId: string | null;
  disabled: boolean;
  inputMode: InputMode;
  isSubmitting: boolean;
  onCancelRun: () => void;
  onChange: (value: string) => void;
  onInputModeChange: (mode: InputMode) => void;
  onSubmit: (value: string) => void;
  value: string;
};

export type InputMode = "voice" | "text";
const releaseVersion = process.env.NEXT_PUBLIC_DAYBOARD_RELEASE?.trim() || "dev";

function recordingErrorMessage(error: unknown, t: (key: string) => string) {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return t("voice.microphonePermission");
    if (error.name === "NotFoundError") return t("voice.microphoneMissing");
    if (error.name === "NotReadableError") return t("voice.microphoneBusy");
  }
  return t("voice.recordingFailed");
}

export function Composer({
  activeRunId,
  disabled,
  inputMode,
  isSubmitting,
  onCancelRun,
  onChange,
  onInputModeChange,
  onSubmit,
  value,
}: ComposerProps) {
  const { t, locale } = useI18n();
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [capabilitiesResolved, setCapabilitiesResolved] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
  const wasSubmittingRef = useRef(isSubmitting);
  const uploadControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      uploadControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void getVoiceCapabilities(controller.signal)
      .then((result) => {
        if (!mountedRef.current) return;
        setCapabilities(result);
        setCapabilitiesResolved(true);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setCapabilities(null);
        setCapabilitiesResolved(true);
      });
    return () => controller.abort();
  }, []);

  const showTextInput = useCallback(() => {
    onInputModeChange("text");
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [onInputModeChange]);

  const handleRecorded = useCallback(
    async (recording: RecordedAudio) => {
      const controller = new AbortController();
      uploadControllerRef.current = controller;
      setVoiceError(null);
      setIsTranscribing(true);
      try {
        const transcript = await transcribeVoice(recording, controller.signal);
        if (!mountedRef.current) return;
        if (!transcript.text?.trim()) throw new Error("Transcription returned no text");
        const recognizedText = transcript.text.trim();
        const draft = value.trim();
        onSubmit(draft ? `${draft} ${recognizedText}` : recognizedText);
      } catch (error) {
        if (
          mountedRef.current &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setVoiceError(userFacingApiError(error, t("voice.transcriptionFailed"), locale));
        }
      } finally {
        if (uploadControllerRef.current === controller) uploadControllerRef.current = null;
        if (mountedRef.current) setIsTranscribing(false);
      }
    },
    [locale, onSubmit, t, value],
  );

  const handleRecorderError = useCallback((error: unknown) => {
    setVoiceError(recordingErrorMessage(error, t));
  }, [t]);

  const handleStartupMeasured = useCallback((metric: VoiceStartupMetric) => {
    void reportVoiceStartupMetric(metric).catch(() => undefined);
  }, []);

  const recorder = useVoiceRecorder({
    maxDurationSeconds: capabilities?.max_duration_seconds ?? 60,
    onError: handleRecorderError,
    onRecorded: handleRecorded,
    onStartupMeasured: handleStartupMeasured,
    release: releaseVersion,
    supportedContentTypes: capabilities?.supported_content_types ?? [],
  });

  const voiceAvailable = Boolean(capabilities?.available && recorder.isSupported);

  useEffect(() => {
    if (wasSubmittingRef.current && !isSubmitting && voiceAvailable) {
      onInputModeChange("voice");
    }
    wasSubmittingRef.current = isSubmitting;
  }, [isSubmitting, onInputModeChange, voiceAvailable]);

  const voiceStatus: VoiceComposerStatus = isTranscribing
    ? "transcribing"
    : recorder.status;
  const unavailableReason = !recorder.isSupported
    ? t("voice.browserUnsupported")
    : !capabilitiesResolved
      ? t("voice.preparing")
      : !capabilities?.available
        ? t("voice.unavailable")
        : null;

  function cancelTranscription() {
    uploadControllerRef.current?.abort();
    uploadControllerRef.current = null;
    setIsTranscribing(false);
  }

  return (
    <div className={styles.wrapper}>
      {voiceError ? (
        <div className={styles.voiceError} role="alert">
          <AlertCircle aria-hidden="true" size={16} />
          <span>{voiceError}</span>
          <button
            aria-label={t("voice.closeNotice")}
            className={styles.dismissButton}
            onClick={() => setVoiceError(null)}
            type="button"
          >
            <X size={15} />
          </button>
        </div>
      ) : null}

      {inputMode === "voice" && !isSubmitting ? (
        <VoiceComposer
          disabled={disabled || !voiceAvailable}
          elapsedSeconds={recorder.elapsedSeconds}
          level={recorder.level}
          maxDurationSeconds={capabilities?.max_duration_seconds ?? 60}
          onCancelRecording={recorder.cancelRecording}
          onCancelTranscription={cancelTranscription}
          onStartRecording={async (pressedAt) => {
            setVoiceError(null);
            await recorder.startRecording(pressedAt);
          }}
          onStopRecording={recorder.stopRecording}
          onSwitchToText={showTextInput}
          status={voiceStatus}
          unavailableReason={unavailableReason}
        />
      ) : (
        <TextComposer
          activeRunId={activeRunId}
          disabled={disabled}
          inputRef={inputRef}
          isSubmitting={isSubmitting}
          onCancelRun={onCancelRun}
          onChange={onChange}
          onSubmit={onSubmit}
          onSwitchToVoice={() => onInputModeChange("voice")}
          value={value}
        />
      )}
    </div>
  );
}
