"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  LoaderCircle,
  Mic,
  SendHorizontal,
  Square,
  X,
} from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { getVoiceCapabilities, transcribeVoice } from "@/features/voice/api";
import type { RecordedAudio, VoiceCapabilities } from "@/features/voice/types";
import { useVoiceRecorder } from "@/features/voice/useVoiceRecorder";
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

function recordingErrorMessage(error: unknown) {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "没有麦克风权限，请在浏览器设置中允许。";
    if (error.name === "NotFoundError") return "没有检测到可用的麦克风。";
    if (error.name === "NotReadableError") return "麦克风暂时无法使用，请检查其他应用。";
  }
  return "无法开始录音，请稍后重试。";
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
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
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
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
        if (mountedRef.current) setCapabilities(result);
      })
      .catch(() => {
        if (mountedRef.current) setCapabilities(null);
      });
    return () => controller.abort();
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
        window.setTimeout(() => inputRef.current?.focus(), 0);
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
    [onTranscript],
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

  const recording = recorder.status === "recording";
  const requesting = recorder.status === "requesting";
  const voiceBusy = recording || requesting || isTranscribing;
  const voiceAvailable = Boolean(capabilities?.available && recorder.isSupported);
  const microphoneTitle = !recorder.isSupported
    ? "当前浏览器不支持录音"
    : capabilities && !capabilities.available
      ? "语音识别暂未配置"
      : "开始语音输入";
  const levels = [0.48, 0.76, 1, 0.68, 0.42];

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

      <form
        className={`${styles.composer} ${recording ? styles.recordingComposer : ""}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (!voiceBusy) onSubmit();
        }}
      >
        {recording ? (
          <button
            aria-label="取消录音"
            className={styles.iconButton}
            onClick={recorder.cancelRecording}
            type="button"
          >
            <X size={20} />
          </button>
        ) : requesting || isTranscribing ? (
          <span className={styles.activityIcon} aria-hidden="true">
            <LoaderCircle className={styles.spinner} size={20} />
          </span>
        ) : (
          <button
            aria-label="语音输入"
            className={styles.iconButton}
            disabled={disabled || isSubmitting || !voiceAvailable}
            onClick={() => {
              setVoiceError(null);
              void recorder.startRecording();
            }}
            title={microphoneTitle}
            type="button"
          >
            <Mic size={20} strokeWidth={2.2} />
          </button>
        )}

        {recording ? (
          <div className={styles.recordingStatus} aria-live="polite">
            <span className={styles.recordingDot} aria-hidden="true" />
            <span className={styles.levelBars} aria-hidden="true">
              {levels.map((weight, index) => (
                <span
                  key={index}
                  style={{ transform: `scaleY(${Math.max(0.2, recorder.level * weight)})` }}
                />
              ))}
            </span>
            <span>{formatDuration(recorder.elapsedSeconds)}</span>
            <span className={styles.durationLimit}>
              / {formatDuration(capabilities?.max_duration_seconds ?? 60)}
            </span>
          </div>
        ) : requesting || isTranscribing ? (
          <div className={styles.processingStatus} aria-live="polite">
            {requesting ? "正在连接麦克风" : "正在识别语音"}
          </div>
        ) : (
          <label className={styles.inputWrap}>
            <span className={styles.srOnly}>输入日程或任务</span>
            <input
              disabled={disabled || isSubmitting}
              onChange={(event) => onChange(event.target.value)}
              placeholder="输入日程或任务"
              ref={inputRef}
              type="text"
              value={value}
            />
          </label>
        )}

        {recording ? (
          <button
            aria-label="停止录音"
            className={styles.recordingStopButton}
            onClick={recorder.stopRecording}
            type="button"
          >
            <Square fill="currentColor" size={16} strokeWidth={2.2} />
          </button>
        ) : isTranscribing ? (
          <button
            aria-label="取消识别"
            className={styles.iconButton}
            onClick={cancelTranscription}
            type="button"
          >
            <X size={20} />
          </button>
        ) : requesting ? (
          <span className={styles.activityIcon} />
        ) : isSubmitting ? (
          <button
            aria-label="停止"
            className={styles.stopButton}
            disabled={!activeRunId}
            onClick={onCancelRun}
            type="button"
          >
            <Square fill="currentColor" size={17} strokeWidth={2.2} />
          </button>
        ) : (
          <button
            aria-label="发送"
            className={styles.sendButton}
            disabled={!value.trim() || disabled}
            type="submit"
          >
            <SendHorizontal size={20} strokeWidth={2.2} />
          </button>
        )}
      </form>
    </div>
  );
}
