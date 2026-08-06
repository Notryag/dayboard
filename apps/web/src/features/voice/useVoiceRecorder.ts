"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { RecordedAudio, VoiceStartupMetric } from "./types";

type RecorderStatus = "idle" | "requesting" | "recording";

type VoiceRecorderOptions = {
  maxDurationSeconds: number;
  onError: (error: unknown) => void;
  onRecorded: (recording: RecordedAudio) => void;
  onStartupMeasured: (metric: VoiceStartupMetric) => void;
  release: string;
  supportedContentTypes: string[];
};

type StartupAttempt = {
  measurementId: string;
  pressedAt: number;
  recorderReadyAt: number | null;
  requestStartedAt: number;
  streamAcquiredAt: number | null;
};

const recordingFormats = [
  { extension: "webm", mimeType: "audio/webm;codecs=opus" },
  { extension: "m4a", mimeType: "audio/mp4" },
  { extension: "ogg", mimeType: "audio/ogg;codecs=opus" },
  { extension: "webm", mimeType: "audio/webm" },
];

const STREAM_WARM_TTL_MS = 15_000;

function baseContentType(mimeType: string) {
  return mimeType.split(";", 1)[0].trim().toLowerCase();
}

function extensionForMimeType(mimeType: string) {
  const contentType = baseContentType(mimeType);
  if (contentType === "audio/mp4" || contentType === "audio/x-m4a") return "m4a";
  if (contentType === "audio/ogg") return "ogg";
  if (contentType === "audio/mpeg" || contentType === "audio/mp3") return "mp3";
  if (contentType === "audio/wav" || contentType === "audio/x-wav") return "wav";
  return "webm";
}

function elapsedMs(start: number, end: number) {
  return Math.round(Math.max(0, end - start) * 100) / 100;
}

function errorName(error: unknown) {
  return error instanceof Error ? error.name.slice(0, 80) : "UnknownError";
}

function subscribeToBrowserCapabilities() {
  return () => undefined;
}

function browserSupportsRecording() {
  return (
    typeof MediaRecorder !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

export function useVoiceRecorder({
  maxDurationSeconds,
  onError,
  onRecorded,
  onStartupMeasured,
  release,
  supportedContentTypes,
}: VoiceRecorderOptions) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const isSupported = useSyncExternalStore(
    subscribeToBrowserCapabilities,
    browserSupportsRecording,
    () => false,
  );
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const warmStreamTimeoutRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const discardRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const startedAtRef = useRef(0);
  const startupAttemptRef = useRef<StartupAttempt | null>(null);
  const mountedRef = useRef(true);
  const onErrorRef = useRef(onError);
  const onRecordedRef = useRef(onRecorded);
  const onStartupMeasuredRef = useRef(onStartupMeasured);

  useEffect(() => {
    onErrorRef.current = onError;
    onRecordedRef.current = onRecorded;
    onStartupMeasuredRef.current = onStartupMeasured;
  }, [onError, onRecorded, onStartupMeasured]);

  const finishStartupMeasurement = useCallback((
    outcome: VoiceStartupMetric["outcome"],
    extra: Pick<VoiceStartupMetric, "press_to_recording_ms" | "recorder_start_call_ms">
      & Partial<Pick<VoiceStartupMetric, "press_to_cancel_ms" | "error_name">>,
  ) => {
    const attempt = startupAttemptRef.current;
    if (!attempt) return;
    startupAttemptRef.current = null;
    onStartupMeasuredRef.current({
      schema_version: 1,
      measurement_id: attempt.measurementId,
      release,
      outcome,
      press_to_request_ms: elapsedMs(attempt.pressedAt, attempt.requestStartedAt),
      get_user_media_ms: attempt.streamAcquiredAt === null
        ? null
        : elapsedMs(attempt.requestStartedAt, attempt.streamAcquiredAt),
      stream_to_recorder_ready_ms:
        attempt.streamAcquiredAt === null || attempt.recorderReadyAt === null
          ? null
          : elapsedMs(attempt.streamAcquiredAt, attempt.recorderReadyAt),
      recorder_start_call_ms: extra.recorder_start_call_ms,
      press_to_recording_ms: extra.press_to_recording_ms,
      press_to_cancel_ms: extra.press_to_cancel_ms ?? null,
      error_name: extra.error_name ?? null,
    });
  }, [release]);

  const clearTimers = useCallback(() => {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
    }
    intervalRef.current = null;
    timeoutRef.current = null;
    animationFrameRef.current = null;
  }, []);

  const stopMonitoring = useCallback(() => {
    clearTimers();
    void audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
  }, [clearTimers]);

  const releaseMedia = useCallback(() => {
    stopMonitoring();
    if (warmStreamTimeoutRef.current !== null) {
      window.clearTimeout(warmStreamTimeoutRef.current);
      warmStreamTimeoutRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, [stopMonitoring]);

  const keepStreamWarm = useCallback(() => {
    stopMonitoring();
    if (warmStreamTimeoutRef.current !== null) {
      window.clearTimeout(warmStreamTimeoutRef.current);
    }
    warmStreamTimeoutRef.current = window.setTimeout(() => {
      warmStreamTimeoutRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }, STREAM_WARM_TTL_MS);
  }, [stopMonitoring]);

  const monitorLevel = useCallback((stream: MediaStream) => {
    if (typeof AudioContext === "undefined") return;
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    const source = context.createMediaStreamSource(stream);
    analyser.fftSize = 256;
    const samples = new Uint8Array(analyser.fftSize);
    source.connect(analyser);
    audioContextRef.current = context;

    const update = () => {
      analyser.getByteTimeDomainData(samples);
      let amplitude = 0;
      for (const sample of samples) amplitude += Math.abs(sample - 128) / 128;
      if (mountedRef.current) setLevel(Math.min(1, (amplitude / samples.length) * 4));
      animationFrameRef.current = window.requestAnimationFrame(update);
    };
    update();
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") recorder.stop();
  }, []);

  const cancelRecording = useCallback(() => {
    const cancelledAt = performance.now();
    finishStartupMeasurement("cancelled", {
      press_to_cancel_ms: startupAttemptRef.current
        ? elapsedMs(startupAttemptRef.current.pressedAt, cancelledAt)
        : undefined,
      press_to_recording_ms: null,
      recorder_start_call_ms: null,
    });
    discardRef.current = true;
    requestGenerationRef.current += 1;
    const recorder = recorderRef.current;
    setStatus("idle");
    setElapsedSeconds(0);
    setLevel(0);
    if (recorder?.state === "recording") recorder.stop();
    else {
      recorderRef.current = null;
      chunksRef.current = [];
      releaseMedia();
    }
  }, [finishStartupMeasurement, releaseMedia]);

  const startRecording = useCallback(async (pressedAt = performance.now()) => {
    if (!isSupported || status !== "idle") return;
    const requestStartedAt = performance.now();
    startupAttemptRef.current = {
      measurementId: crypto.randomUUID(),
      pressedAt,
      recorderReadyAt: null,
      requestStartedAt,
      streamAcquiredAt: null,
    };
    setStatus("requesting");
    setElapsedSeconds(0);
    setLevel(0);
    discardRef.current = false;
    const requestGeneration = ++requestGenerationRef.current;

    try {
      let stream = streamRef.current;
      const canReuseStream = stream?.getAudioTracks().some(
        (track) => track.readyState === "live",
      );
      if (!canReuseStream) {
        releaseMedia();
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            autoGainControl: true,
            echoCancellation: true,
            noiseSuppression: true,
          },
          video: false,
        });
      } else if (warmStreamTimeoutRef.current !== null) {
        window.clearTimeout(warmStreamTimeoutRef.current);
        warmStreamTimeoutRef.current = null;
      }
      if (!stream) throw new Error("Microphone stream is unavailable");
      if (!mountedRef.current || requestGeneration !== requestGenerationRef.current) {
        if (!canReuseStream) stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const streamAcquiredAt = performance.now();
      if (startupAttemptRef.current) {
        startupAttemptRef.current.streamAcquiredAt = streamAcquiredAt;
      }
      streamRef.current = stream;
      const allowedTypes = new Set(supportedContentTypes.map(baseContentType));
      const format = recordingFormats.find(
        (candidate) =>
          allowedTypes.has(baseContentType(candidate.mimeType)) &&
          MediaRecorder.isTypeSupported(candidate.mimeType),
      );
      const recorder = format
        ? new MediaRecorder(stream, { mimeType: format.mimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        discardRef.current = true;
        onErrorRef.current(new Error("MediaRecorder failed"));
        if (recorder.state === "recording") recorder.stop();
      };
      recorder.onstop = () => {
        const discarded = discardRef.current;
        const mimeType = recorder.mimeType || chunksRef.current[0]?.type || format?.mimeType || "";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        recorderRef.current = null;
        chunksRef.current = [];
        keepStreamWarm();
        if (!mountedRef.current) return;
        setStatus("idle");
        setLevel(0);
        if (discarded) return;
        if (!blob.size || !mimeType) {
          onErrorRef.current(new Error("Recorded audio is empty"));
          return;
        }
        onRecordedRef.current({
          blob,
          extension: format?.extension ?? extensionForMimeType(mimeType),
          mimeType,
        });
      };

      const recorderReadyAt = performance.now();
      if (startupAttemptRef.current) {
        startupAttemptRef.current.recorderReadyAt = recorderReadyAt;
      }
      recorder.start(250);
      const recordingAt = performance.now();
      finishStartupMeasurement("recording", {
        press_to_recording_ms: startupAttemptRef.current
          ? elapsedMs(startupAttemptRef.current.pressedAt, recordingAt)
          : null,
        recorder_start_call_ms: elapsedMs(recorderReadyAt, recordingAt),
      });
      startedAtRef.current = performance.now();
      setStatus("recording");
      try {
        monitorLevel(stream);
      } catch {
        setLevel(0);
      }
      intervalRef.current = window.setInterval(() => {
        const elapsed = Math.floor((performance.now() - startedAtRef.current) / 1000);
        if (mountedRef.current) setElapsedSeconds(Math.min(maxDurationSeconds, elapsed));
      }, 250);
      timeoutRef.current = window.setTimeout(stopRecording, maxDurationSeconds * 1000);
    } catch (error) {
      finishStartupMeasurement("failed", {
        error_name: errorName(error),
        press_to_recording_ms: null,
        recorder_start_call_ms: null,
      });
      if (requestGeneration !== requestGenerationRef.current) return;
      releaseMedia();
      recorderRef.current = null;
      if (mountedRef.current) setStatus("idle");
      onErrorRef.current(error);
    }
  }, [
    isSupported,
    maxDurationSeconds,
    finishStartupMeasurement,
    monitorLevel,
    keepStreamWarm,
    releaseMedia,
    status,
    stopRecording,
    supportedContentTypes,
  ]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestGenerationRef.current += 1;
      discardRef.current = true;
      const recorder = recorderRef.current;
      if (recorder?.state === "recording") recorder.stop();
      releaseMedia();
    };
  }, [releaseMedia]);

  return {
    cancelRecording,
    elapsedSeconds,
    isSupported,
    level,
    startRecording,
    status,
    stopRecording,
  };
}
