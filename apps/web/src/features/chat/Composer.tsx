"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, X } from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { getVoiceCapabilities, transcribeVoice } from "@/features/voice/api";
import type { RecordedAudio, VoiceCapabilities } from "@/features/voice/types";
import { useVoiceRecorder } from "@/features/voice/useVoiceRecorder";
import { TextComposer } from "./TextComposer";
import { VoiceComposer, type VoiceComposerStatus } from "./VoiceComposer";
import styles from "./Composer.module.css";

type ComposerProps = {
  activeRunId: string | null;
  disabled: boolean;
  isSubmitting: boolean;
  onCancelRun: () => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onTranscript: (text: string) => void;
  value: string;
};

type InputMode = "voice" | "text";

function recordingErrorMessage(error: unknown) {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "没有麦克风权限，请在浏览器设置中允许。";
    if (error.name === "NotFoundError") return "没有检测到可用的麦克风。";
    if (error.name === "NotReadableError") return "麦克风暂时无法使用，请检查其他应用。";
  }
  return "无法开始录音，请稍后重试。";
}

export function Composer({
  activeRunId,
  disabled,
  isSubmitting,
  onCancelRun,
  onChange,
  onSubmit,
  onTranscript,
  value,
}: ComposerProps) {
  const [inputMode, setInputMode] = useState<InputMode>("voice");
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
    setInputMode("text");
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, []);

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
        onTranscript(transcript.text.trim());
        showTextInput();
      } catch (error) {
        if (
          mountedRef.current &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setVoiceError(userFacingApiError(error, "语音识别失败，请重新录制。"));
        }
      } finally {
        if (uploadControllerRef.current === controller) uploadControllerRef.current = null;
        if (mountedRef.current) setIsTranscribing(false);
      }
    },
    [onTranscript, showTextInput],
  );

  const handleRecorderError = useCallback((error: unknown) => {
    setVoiceError(recordingErrorMessage(error));
  }, []);

  const recorder = useVoiceRecorder({
    maxDurationSeconds: capabilities?.max_duration_seconds ?? 60,
    onError: handleRecorderError,
    onRecorded: handleRecorded,
    supportedContentTypes: capabilities?.supported_content_types ?? [],
  });

  const voiceAvailable = Boolean(capabilities?.available && recorder.isSupported);

  useEffect(() => {
    if (wasSubmittingRef.current && !isSubmitting && voiceAvailable) {
      setInputMode("voice");
    }
    wasSubmittingRef.current = isSubmitting;
  }, [isSubmitting, voiceAvailable]);

  const voiceStatus: VoiceComposerStatus = isTranscribing
    ? "transcribing"
    : recorder.status;
  const unavailableReason = !recorder.isSupported
    ? "当前浏览器不支持语音输入"
    : !capabilitiesResolved
      ? "正在准备语音输入"
      : !capabilities?.available
        ? "语音输入暂不可用"
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
            aria-label="关闭提示"
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
          onStartRecording={async () => {
            setVoiceError(null);
            await recorder.startRecording();
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
          onSwitchToVoice={() => setInputMode("voice")}
          value={value}
        />
      )}
    </div>
  );
}
