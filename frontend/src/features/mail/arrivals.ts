import { useQueryClient } from "@tanstack/vue-query"
import { getCurrentScope, onScopeDispose } from "vue"

import type { ConnectorPublic } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import { t } from "@/shared/i18n"
import { realtime } from "@/shared/realtime/client"
import { useToast } from "@/shared/ui"

import { mailKey } from "./api"

/**
 * New letters in the person's own mailboxes, told while they are signed in
 * (D372). The server watches only while this is subscribed.
 */
export const ARRIVALS_TOPIC = "mail.arrivals"

/** One report, as app/connectors/mail_arrivals.py sends it. */
export interface MailArrivalsEvent {
  connector_id: string
  unseen: number
  count: number
  newest: { subject: string; sender: { name: string; address: string } | null }[]
}

function isArrivals(payload: unknown): payload is MailArrivalsEvent {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "connector_id" in payload &&
    "count" in payload &&
    "newest" in payload
  )
}

/** What the notification says, or null when nothing arrived. Pure. */
export function arrivalText(event: MailArrivalsEvent, mailbox: string): string | null {
  if (event.count <= 0) return null
  const newest = event.newest[0]
  if (event.count === 1 && newest !== undefined) {
    const who = newest.sender === null ? t("mail.nobody") : newest.sender.name || newest.sender.address
    return t("mail.arrivals.one", {
      mailbox,
      who,
      subject: newest.subject || t("mail.no_subject"),
    })
  }
  return t("mail.arrivals.many", { mailbox, n: event.count })
}

/**
 * Listen for as long as the caller lives; called once, from the workspace,
 * and released with it, as the health topic is (see realtime.md, two traps).
 */
export function useMailArrivals(open: (connector: ConnectorPublic) => void) {
  const queryClient = useQueryClient()
  const connectors = useConnectors()
  const toast = useToast()

  const stop = realtime().subscribe(ARRIVALS_TOPIC, (payload) => {
    if (!isArrivals(payload)) return
    // The open tab's lists and counts are read again either way.
    void queryClient.invalidateQueries({ queryKey: mailKey(payload.connector_id) })
    const connector = connectors.data.value?.data.find((one) => one.id === payload.connector_id)
    if (connector === undefined) return
    const text = arrivalText(payload, connector.name)
    if (text === null) return
    toast.offer(text, { label: t("mail.arrivals.open"), onClick: () => open(connector) })
  })

  if (getCurrentScope()) onScopeDispose(stop)
  return { stop }
}
