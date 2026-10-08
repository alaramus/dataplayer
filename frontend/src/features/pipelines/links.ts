/**
 * Links between the rows of a pipeline's cards (D176), as plain decisions.
 *
 * What a link can do is the server's answer — the same offers Paste and the
 * pair window get (D164, D167) — and so are the order a run takes them in and
 * what each did in it (D177). No kind of paste is named on this side; these
 * only draw, keep and word what came back.
 */

import type {
  Card, CardRow, HintLink, Link, LinkEnd, LinkPlace, LinkRun, PasteOffer, PipelineRunPublic, ResultRow,
} from "@/client"
import { ICONS } from "@/features/catalog/nodes"
import { ageLabel } from "@/shared/freshness/freshness"
import type { GraphEdge, GraphEdgeTone, GraphPort } from "@/shared/graph/model"

import { rowId } from "./model"
import type { MadeRow } from "./model"

const MADE = "made:"

/** The node a row of the canvas names; the top of a connection names none. */
export function nodeIdOf(portId: string): string | null {
  return portId.startsWith("node:") ? portId.slice("node:".length) : null
}

/** A row of the canvas as a link's end: a node, the top, or what a link makes (D178). */
export function endOf(port: GraphPort): LinkEnd {
  if (port.portId.startsWith(MADE)) {
    return { card_id: port.nodeId, node_id: null, made_by: port.portId.slice(MADE.length) }
  }
  return { card_id: port.nodeId, node_id: nodeIdOf(port.portId) }
}

/** The canvas's row an end names. */
export function endRowId(end: LinkEnd): string {
  return end.made_by == null ? rowId(end.node_id) : `${MADE}${end.made_by}`
}

function endpoint(end: LinkEnd) {
  return { nodeId: end.card_id, portIds: [endRowId(end)] }
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
 * in the run shown — the last, or one pressed in the history (D180).
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
  return a.card_id === b.card_id && endRowId(a) === endRowId(b)
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
  if (from.node_id == null && from.made_by == null) {
    return "The top of a connection is a place things arrive in, not something to take"
  }
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

/**
 * The links that go with these: every one reading or writing into what they
 * make, however far along (D178).
 */
export function dependents(links: readonly Link[], going: ReadonlySet<string>): Link[] {
  const gone = new Set(going)
  const found: Link[] = []
  let grew = true
  while (grew) {
    grew = false
    for (const link of links) {
      if (gone.has(link.id)) continue
      if ([link.source, link.target].some((end) => end.made_by != null && gone.has(end.made_by))) {
        gone.add(link.id)
        found.push(link)
        grew = true
      }
    }
  }
  return found
}

/** Links that stay when a card keeps only these rows, and what they make with them. */
export function keptLinks(links: readonly Link[], cardId: string, rows: readonly CardRow[]): Link[] {
  const held = new Set(rows.map((row) => rowId(row.node_id)))
  const stays = (end: LinkEnd) => end.card_id !== cardId || end.made_by != null || held.has(rowId(end.node_id))
  const going = new Set(links.filter((link) => !(stays(link.source) && stays(link.target))).map((link) => link.id))
  for (const link of dependents(links, going)) going.add(link.id)
  return links.filter((link) => !going.has(link.id))
}

/**
 * What each link makes, as a row below the one it writes into (D178). The
 * server names it; the link as drawn says which card and row it goes under.
 */
export function madeRows(
  results: readonly ResultRow[],
  links: readonly Link[],
  order: ReadonlyMap<string, LinkPlace>
): MadeRow[] {
  return results.flatMap((result) => {
    const link = links.find((one) => one.id === result.link_id)
    if (link === undefined) return []
    const place = order.get(link.id)
    return [{
      cardId: link.target.card_id,
      after: endRowId(link.target),
      row: {
        id: `${MADE}${link.id}`,
        label: result.name,
        detail: place === undefined ? "to be made" : `← ${String(place.number)}`,
        icon: ICONS[result.kind],
        made: true,
      },
    }]
  })
}

/** The links making what an end is, nearest first: what its answer depends on. */
export function chainOf(links: readonly Link[], end: LinkEnd): Link[] {
  const chain: Link[] = []
  let at: LinkEnd | undefined = end
  while (at?.made_by != null) {
    const maker: Link | undefined = links.find((one) => one.id === at?.made_by)
    if (maker === undefined || chain.includes(maker)) break
    chain.push(maker)
    at = maker.source
  }
  return chain
}

/** How a card and its row are named in a sentence about a link. */
export type EndNamer = (end: LinkEnd) => string

/** What the link does, in the words the panel says it: "Save as CSV: Sales · orders → Files · reports". */
export function sentence(link: Link, name: EndNamer): string {
  return `${link.title}: ${name(link.source)} → ${name(link.target)}`
}

/** Whether the link still needs its table or column choices (D176): open its window at once. */
export function needsDialog(link: Link, workflow: string): boolean {
  if (workflow === "new-relation") return link.name == null || (link.columns ?? []).length === 0
  if (workflow === "into-relation") return (link.columns ?? []).length === 0
  return false
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

/**
 * A link's part in the run shown, as its panel says it: "Done 3m ago:
 * orders.csv saved in reports". `past` when that is an older run than the last.
 */
export function runWords(
  linkRun: LinkRun | undefined, run: PipelineRunPublic | null | undefined, now: number, past = false
): string {
  if (run == null) return "Not run yet"
  if (linkRun === undefined) return past ? "Drawn since this run" : "Drawn since the last run"
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
