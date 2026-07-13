export type VoiceCapabilities = {
  available: boolean;
  max_duration_seconds: number;
  max_upload_bytes: number;
  supported_content_types: string[];
};

export type VoiceTranscript = {
  id: string;
  status: "processing" | "completed" | "failed";
  text: string | null;
  duration_ms: number | null;
};

export type RecordedAudio = {
  blob: Blob;
  extension: string;
  mimeType: string;
};
