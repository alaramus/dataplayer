/**
 * Callout blocks an agent writes into a document.
 *
 * A fence named `summary`, `decision`, `risk` and so on is still a fenced code
 * block in any other Markdown tool — that is the point of the convention — and
 * here it is shown as what it means. See D50.
 */

export const AGENT_KINDS = [
  "summary",
  "warning",
  "decision",
  "risk",
  "file",
  "verification",
  "command",
  "result",
  "question",
] as const

export type AgentKind = (typeof AGENT_KINDS)[number]

const KINDS = new Set<string>(AGENT_KINDS)

/** The fence info string of a callout, with the optional `callout:` prefix. */
export function agentKindOf(language: string): AgentKind | null {
  const name = language.startsWith("callout:") ? language.slice("callout:".length) : language
  return KINDS.has(name) ? (name as AgentKind) : null
}

export interface AgentLook {
  label: string
  icon: string
  /** The token this kind is coloured by: the colour is the meaning. */
  accent: string
}

export const AGENT_LOOKS: Record<AgentKind, AgentLook> = {
  summary: { label: "summary", icon: "summarize", accent: "var(--dp-callout-note)" },
  warning: { label: "warning", icon: "warning_amber", accent: "var(--dp-callout-caution)" },
  decision: { label: "decision", icon: "gavel", accent: "var(--dp-callout-decision)" },
  risk: { label: "risk", icon: "crisis_alert", accent: "var(--dp-callout-caution)" },
  file: { label: "file", icon: "draft", accent: "var(--dp-callout-note)" },
  verification: { label: "verification", icon: "fact_check", accent: "var(--dp-callout-done)" },
  command: { label: "command", icon: "terminal", accent: "var(--dp-callout-plain)" },
  result: { label: "result", icon: "task_alt", accent: "var(--dp-callout-done)" },
  question: { label: "question", icon: "help_outline", accent: "var(--dp-callout-question)" },
}

export interface AgentField {
  key: string
  value: string
}

export interface AgentContent {
  fields: AgentField[]
  body: string
}

const FIELD = /^([A-Za-z][\w -]{0,30}):\s*(.+)$/

/**
 * Split a callout into its leading `Key: value` lines and the rest.
 *
 * Only the run of fields at the top is read that way: a colon in the middle of
 * a sentence further down is a sentence, not a field.
 */
export function readAgentBlock(code: string): AgentContent {
  const fields: AgentField[] = []
  const body: string[] = []
  let reading = true

  for (const line of code.trim().split("\n")) {
    const field = reading ? FIELD.exec(line) : null
    if (field !== null && field[1] !== undefined && field[2] !== undefined) {
      fields.push({ key: field[1], value: field[2] })
      continue
    }
    reading = false
    body.push(line)
  }

  const rest = body.join("\n").trim()
  return { fields, body: rest === "" && fields.length === 0 ? code.trim() : rest }
}
