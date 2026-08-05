export type { VoiceCapabilities, VoiceStartupMetric, VoiceTranscript } from "@/lib/api/types";

export type RecordedAudio = {
  blob: Blob;
  extension: string;
  mimeType: string;
};
