"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { RecordedAudio } from "./types";

type RecorderStatus = "idle" | "requesting" | "recording";

type VoiceRecorderOptions = {
  maxDurationSeconds: number;
  onError: (error: unknown) => void;
  onRecorded: (recording: RecordedAudio) => void;
  supportedContentTypes: string[];
};

const recordingFormats = [
  { extension: "webm", mimeType: "audio/webm;codecs=opus" },
  { extension: "m4a", mimeType: "audio/mp4" },
  { extension: "ogg", mimeType: "audio/ogg;codecs=opus" },
  { extension: "webm", mimeType: "audio/webm" },
];

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
  const chunksRef = useRef<Blob[]>([]);
  const discardRef = useRef(false);
  const startedAtRef = useRef(0);
  const mountedRef = useRef(true);
  const onErrorRef = useRef(onError);
  const onRecordedRef = useRef(onRecorded);

  useEffect(() => {
    onErrorRef.current = onError;
    onRecordedRef.current = onRecorded;
  }, [onError, onRecorded]);

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

  const releaseMedia = useCallback(() => {
    clearTimers();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
  }, [clearTimers]);

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
    discardRef.current = true;
    stopRecording();
  }, [stopRecording]);

  const startRecording = useCallback(async () => {
    if (!isSupported || status !== "idle") return;
    setStatus("requesting");
    setElapsedSeconds(0);
    setLevel(0);
    discardRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        },
        video: false,
      });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
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
        releaseMedia();
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

      recorder.start(250);
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
      releaseMedia();
      recorderRef.current = null;
      if (mountedRef.current) setStatus("idle");
      onErrorRef.current(error);
    }
  }, [
    isSupported,
    maxDurationSeconds,
    monitorLevel,
    releaseMedia,
    status,
    stopRecording,
    supportedContentTypes,
  ]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
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
