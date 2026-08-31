import type { AudioContent, VideoContent } from "@/client"
import { formatSize } from "@/features/catalog/nodes"

/**
 * What a player's head says about a file before it plays.
 *
 * A pure function so the wording is tested without mounting anything, and so
 * the two elements — one for sound, one for a recording — say the same kind of
 * thing. Only what the source verified appears: a duration the container did
 * not state is left out rather than shown as zero (D52).
 */
export function mediaDetails(media: AudioContent | VideoContent): string {
  const parts: string[] = [formatName(media.media_type)]
  if (media.kind === "video" && media.width && media.height) {
    parts.push(`${String(media.width)} × ${String(media.height)}`)
  }
  if (media.kind === "audio") {
    if (media.channels) parts.push(channels(media.channels))
    if (media.sample_rate) parts.push(`${String(media.sample_rate / 1000)} kHz`)
  }
  if (media.duration_seconds !== null && media.duration_seconds !== undefined) {
    parts.push(formatDuration(media.duration_seconds))
  }
  parts.push(formatSize(media.size_bytes))
  return parts.join(" · ")
}

/** The container, named as a person would say it rather than as a MIME type. */
function formatName(mediaType: string): string {
  const NAMES: Record<string, string> = {
    "audio/mpeg": "MP3",
    "audio/wav": "WAV",
    "audio/ogg": "Ogg",
    "audio/mp4": "MP4 audio",
    "audio/flac": "FLAC",
    "video/mp4": "MP4",
    "video/webm": "WebM",
    "video/ogg": "Ogg video",
    "video/quicktime": "QuickTime",
  }
  return NAMES[mediaType] ?? mediaType
}

function channels(count: number): string {
  if (count === 1) return "mono"
  if (count === 2) return "stereo"
  return `${String(count)} channels`
}

/** Hours only when there are any, and always two digits for what follows. */
export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const rest = whole % 60
  const padded = `${String(minutes).padStart(hours > 0 ? 2 : 1, "0")}:${String(rest).padStart(2, "0")}`
  return hours > 0 ? `${String(hours)}:${padded}` : padded
}
