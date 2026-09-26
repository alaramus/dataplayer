/**
 * Links between the rows of a pipeline's cards (D176), as plain decisions.
 *
 * What a link can do is the server's answer — the same offers Paste and the
 * pair window get (D164, D167) — so no kind of paste is named on this side;
 * these only draw, keep and word what came back.
 */

import type { Card, CardRow, HintLink, Link, LinkEnd, LinkRun, PasteOffer } from "@/client"
import { ageLabel } from "@/shared/freshness/freshness"
import type { GraphEdge, GraphPort } from "@/shared/graph/model"

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

export function linkEdge(link: Link): GraphEdge {
  return { id: link.id, source: endpoint(link.source), target: endpoint(link.target), label: link.title, directed: true }
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

/** What running the link still needs chosen, or nothing when it is ready. */
export function missingChoice(link: Link, offer: PasteOffer | undefined): string | null {
  const workflow = offer?.workflow ?? "run"
  if (workflow === "new-relation" && (link.name == null || !link.columns?.length)) {
    return "Choose the new table's name and columns first"
  }
  if (workflow === "into-relation" && !link.columns?.length) return "Pair the columns first"
  return null
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

const OUTCOME_WORDS: Record<LinkRun["outcome"], string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
}

/** The last run, as the panel says it: "Done 3m ago: orders.csv saved in reports". */
export function runWords(run: LinkRun | undefined, now: number): string {
  if (run === undefined) return "Not run yet"
  const at = Date.parse(run.finished_at ?? run.started_at)
  const when = Number.isNaN(at) ? "" : ` ${ageLabel(now - at)} ago`
  const said = run.message ? `: ${run.message}` : ""
  return `${OUTCOME_WORDS[run.outcome]}${run.outcome === "running" ? "" : when}${said}`
}

export const CONFLICT_CHOICES = [
  { label: "Stop and say so", value: "refuse" },
  { label: "Keep both", value: "rename" },
  { label: "Replace it", value: "replace" },
] as const
