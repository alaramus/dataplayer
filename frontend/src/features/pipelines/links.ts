/**
 * Links between the rows of a pipeline's cards (D176), as plain decisions.
 *
 * What a link can do is the server's answer — the same offers Paste and the
 * pair window get (D164, D167) — and so are the order a run takes them in and
 * what each did in it (D177). No kind of paste is named on this side; these
 * only draw, keep and word what came back.
 */

import type {
  Card, CardRow, HintLink, Link, LinkEnd, LinkPlace, LinkRun, PasteOffer, PipelineRunPublic,
} from "@/client"
import { ageLabel } from "@/shared/freshness/freshness"
import type { GraphEdge, GraphEdgeTone, GraphPort } from "@/shared/graph/model"

import { rowId } from "./model"

/** The node a row of the canvas names; the top of a connection names none. */
export function nodeIdOf(portId: string): string | null {
  return portId.startsWith("node:") ? portId.slice("node:".length) : null
}

export function endOf(port: GraphPort): LinkEnd {
  return { card_id: port.nodeId, node_id: nodeIdOf(port.portId) }
}

function endpoint(end: LinkEnd) {
  return { nodeId: end.card_id, portIds: [rowId(end.node_id)] }
}

/** A result's colour on its line; a link still waiting keeps the plain one. */
const TONES: Record<LinkRun["outcome"], GraphEdgeTone | undefined> = {
  waiting: undefined,
  running: "info",
  done: "success",
  failed: "error",
  not_run: "muted",
}

/**
 * A link as its line: numbered by its place in a run, the number in the
 * caution colour where a circle was broken at it, and coloured by what it did
 * in the last run.
 */
export function linkEdge(link: Link, place?: LinkPlace, run?: LinkRun): GraphEdge {
  const edge: GraphEdge = {
    id: link.id, source: endpoint(link.source), target: endpoint(link.target), label: link.title, directed: true,
  }
  const tone = run === undefined ? undefined : TONES[run.outcome]
  return {
    ...edge,
    ...(place === undefined ? {} : { badge: String(place.number) }),
    ...(place?.circle ? { caution: place.circle } : {}),
    ...(tone === undefined ? {} : { tone }),
  }
}

export const HINT_PREFIX = "hint:"

export function hintEdges(hints: readonly HintLink[]): GraphEdge[] {
  return hints.map((hint, index) => ({
    id: `${HINT_PREFIX}${String(index)}`,
    source: endpoint(hint.source),
    target: endpoint(hint.target),
    label: hint.titles.join(" · "),
    directed: true,
    dashed: true,
  }))
}

export function hintOf(hints: readonly HintLink[], edgeId: string): HintLink | null {
  if (!edgeId.startsWith(HINT_PREFIX)) return null
  return hints[Number(edgeId.slice(HINT_PREFIX.length))] ?? null
}

function sameEnd(a: LinkEnd, b: LinkEnd): boolean {
  return a.card_id === b.card_id && (a.node_id ?? null) === (b.node_id ?? null)
}

/** The link already drawn between these two rows, that way round. */
export function linkBetween(links: readonly Link[], from: LinkEnd, to: LinkEnd): Link | null {
  return links.find((link) => sameEnd(link.source, from) && sameEnd(link.target, to)) ?? null
}

/** Why these two rows cannot be joined before anything is asked, or nothing. */
export function joinProblem(cards: readonly Card[], from: LinkEnd, to: LinkEnd): string | null {
  const source = cards.find((card) => card.id === from.card_id)
  const target = cards.find((card) => card.id === to.card_id)
  if (source === undefined || target === undefined) return "That card is no longer on the canvas"
  if (from.node_id == null) return "The top of a connection is a place things arrive in, not something to take"
  if (source.connector_id === target.connector_id) {
    return "Both ends are in one connection: use Paste in its catalog for that"
  }
  return null
}

/** The offers a link may run: available, or held back only by a taken name. */
export function usable(offers: readonly PasteOffer[]): PasteOffer[] {
  return offers.filter((offer) => offer.available || offer.name_conflict === true)
}

/** Why no link was drawn: the first reason the offers give. */
export function refusal(offers: readonly PasteOffer[]): string {
  return offers.find((offer) => offer.reason)?.reason ?? "Nothing can go from that row into this one"
}

/** A new link doing what this offer does, with no choice made yet. */
export function linkFromOffer(id: string, from: LinkEnd, to: LinkEnd, offer: PasteOffer): Link {
  return { id, source: from, target: to, kind: offer.kind, title: offer.title, conflict: "refuse", name: null, columns: null }
}

/** The same link doing what another offer does: its choices were the other's. */
export function withOffer(link: Link, offer: PasteOffer): Link {
  if (link.kind === offer.kind) return link
  return { ...link, kind: offer.kind, title: offer.title, conflict: "refuse", name: null, columns: null }
}

/** Links that stay when a card keeps only these rows. */
export function keptLinks(links: readonly Link[], cardId: string, rows: readonly CardRow[]): Link[] {
  const held = new Set(rows.map((row) => rowId(row.node_id)))
  const stays = (end: LinkEnd) => end.card_id !== cardId || held.has(rowId(end.node_id))
  return links.filter((link) => stays(link.source) && stays(link.target))
}

/** How a card and its row are named in a sentence about a link. */
export type EndNamer = (end: LinkEnd) => string

/** What the link does, in the words the panel says it: "Save as CSV: Sales · orders → Files · reports". */
export function sentence(link: Link, name: EndNamer): string {
  return `${link.title}: ${name(link.source)} → ${name(link.target)}`
}

/** The ends of these links, as a list a confirmation names. */
export function listed(links: readonly Link[], name: EndNamer): string {
  return links.map((link) => `${name(link.source)} → ${name(link.target)}`).join("; ")
}

/** Whether a run is still going: its job not yet ended. */
export function isRunning(run: PipelineRunPublic | null | undefined): boolean {
  return run?.state === "queued" || run?.state === "running"
}

/** Why Run is off, or nothing when it can be pressed. */
export function runProblem(links: readonly Link[], run: PipelineRunPublic | null | undefined): string | null {
  if (links.length === 0) return "Draw a link first"
  if (isRunning(run)) return "This pipeline is running; Stop is in the activity below"
  return null
}

function ago(at: string | null | undefined, now: number): string {
  const time = Date.parse(at ?? "")
  return Number.isNaN(time) ? "" : ` ${ageLabel(now - time)} ago`
}

/** The last run in the head: "Running 2 of 5", "Last run 3m ago: All 5 links ran". */
export function runSummary(run: PipelineRunPublic | null | undefined, now: number): string {
  if (run == null) return "Not run yet"
  if (isRunning(run)) {
    const at = run.links.findIndex((one) => one.outcome === "running")
    return at < 0 ? "Starting" : `Running ${String(at + 1)} of ${String(run.links.length)}`
  }
  const said = run.message ? `: ${run.message}` : ""
  return `Last run${ago(run.finished_at ?? run.started_at, now)}${said}`
}

/** A link's part in the last run, as its panel says it: "Done 3m ago: orders.csv saved in reports". */
export function runWords(linkRun: LinkRun | undefined, run: PipelineRunPublic | null | undefined, now: number): string {
  if (run == null) return "Not run yet"
  if (linkRun === undefined) return "Drawn since the last run"
  const said = linkRun.message ? `: ${linkRun.message}` : ""
  switch (linkRun.outcome) {
    case "waiting": return "Waiting for the links before it"
    case "running": return "Running"
    case "not_run": return "Not run: the run stopped before it"
    case "done": return `Done${ago(linkRun.finished_at, now)}${said}`
    case "failed": return `Failed${ago(linkRun.finished_at, now)}${said}`
  }
}

export const CONFLICT_CHOICES = [
  { label: "Stop and say so", value: "refuse" },
  { label: "Keep both", value: "rename" },
  { label: "Replace it", value: "replace" },
] as const
