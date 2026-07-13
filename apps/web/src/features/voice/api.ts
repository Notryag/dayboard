import { apiFetch } from "@/lib/api/client";
import type { RecordedAudio, VoiceCapabilities, VoiceTranscript } from "./types";

export async function getVoiceCapabilities(signal?: AbortSignal): Promise<VoiceCapabilities> {
  const response = await apiFetch("/api/voice/capabilities", { signal });
  return response.json() as Promise<VoiceCapabilities>;
}

export async function transcribeVoice(
  recording: RecordedAudio,
  signal?: AbortSignal,
): Promise<VoiceTranscript> {
  const form = new FormData();
  const filename = `command-${Date.now()}.${recording.extension}`;
  form.append("audio", recording.blob, filename);
  form.append("language", "zh");
  const response = await apiFetch("/api/voice/transcriptions", {
    method: "POST",
    body: form,
    signal,
  });
  return response.json() as Promise<VoiceTranscript>;
}
