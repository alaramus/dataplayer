/** How much of the table is written: what is on screen, or everything. */
export type DownloadScope = "page" | "all"

/**
 * Where it goes.
 *
 * The two used to happen together — the browser got the file and a copy stayed
 * in personal storage — so a person who wanted one of them got the other as
 * litter. They are a choice now, and each button says which it is (D28).
 */
export type DownloadDestination = "browser" | "files"

export {
  filenameFromDisposition,
  saveBrowserDownload,
  saveNativeDownload,
} from "@/shared/download"
