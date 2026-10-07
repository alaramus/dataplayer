/**
 * What the browser reads aloud: prose without the marks around it.
 *
 * Code fences, images, link targets and Markdown punctuation are not speech,
 * so they are left out rather than spelled. Plain sources skip this and read
 * as they are: stripping `*` from `SELECT *` would read the opposite of what
 * is on screen.
 */
export function plainSpeechText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*_~`>#-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}
