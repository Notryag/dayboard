export type { VoiceCapabilities, VoiceTranscript } from "@/lib/api/types";

export type RecordedAudio = {
  blob: Blob;
  extension: string;
  mimeType: string;
};
