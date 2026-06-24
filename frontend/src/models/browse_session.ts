export type BrowseSessionStatus = 'opening' | 'active' | 'closed' | 'error';

export type SessionDownloadStatus = 'running' | 'assembling' | 'done' | 'error' | 'cancelled';

export interface SessionDownload {
  id: string;
  url: string;
  output_name: string;
  status: SessionDownloadStatus;
  progress: number;
  done_segments: number;
  total_segments: number;
  logs: string[];
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface HlsStream {
  bandwidth: number;
  resolution: string | null;
  codecs: string | null;
  frame_rate: number | null;
  video_range: string | null;
}

export interface AudioTrack {
  language: string | null;
  name: string;
  default: boolean;
}

export interface SubtitleTrack {
  language: string | null;
  name: string;
  forced: boolean;
}

export interface HlsCandidate {
  url: string;
  type: 'master' | 'media' | 'unknown';
  duration_s: number | null;
  streams: HlsStream[];
  audio_tracks: AudioTrack[];
  subtitle_tracks: SubtitleTrack[];
  intercepted_at: string;
}

export interface BrowseSession {
  id: string;
  status: BrowseSessionStatus;
  url: string;
  created_at: string;
  closed_at: string | null;
  error: string | null;
  candidates: HlsCandidate[];
  downloads: SessionDownload[];
  close_when_done: boolean;
}
