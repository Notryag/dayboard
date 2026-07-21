import { apiClient, requireApiData } from "@/lib/api/typedClient";
import type { RecordedAudio, VoiceCapabilities, VoiceTranscript } from "./types";

export async function getVoiceCapabilities(signal?: AbortSignal): Promise<VoiceCapabilities> {
  const { data } = await apiClient.GET("/api/voice/capabilities", { signal });
  return requireApiData(data);
}

export async function transcribeVoice(
  recording: RecordedAudio,
  signal?: AbortSignal,
): Promise<VoiceTranscript> {
  const form = new FormData();
  const filename = `command-${Date.now()}.${recording.extension}`;
  form.append("audio", recording.blob, filename);
  form.append("language", "zh");
  const { data } = await apiClient.POST("/api/voice/transcriptions", {
    body: { audio: filename, language: "zh" },
    bodySerializer: () => form,
    signal,
  });
  return requireApiData(data);
}
