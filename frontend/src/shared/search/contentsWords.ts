/**
 * The words of the searches inside files started in this tab (S7), for
 * "Search again" once the server has let their matches go.
 *
 * In memory only: never in storage, gone with the page, and emptied on
 * sign-out, as the server never writes them down either.
 */
const wordsOfJobs = new Map<string, string>()

export function rememberContentsWords(jobId: string, words: string): void {
  wordsOfJobs.set(jobId, words)
}

export function contentsWordsOf(jobId: string): string | null {
  return wordsOfJobs.get(jobId) ?? null
}

/** Between accounts: the words were somebody else's. */
export function forgetContentsWords(): void {
  wordsOfJobs.clear()
}
