import { createRealtimeSocket } from "@/shared/realtime/socket"
import type { RealtimeSocket } from "@/shared/realtime/socket"
import { useAuthStore } from "@/stores/auth"
import { serverUrl } from "@/shared/servers/context"

/**
 * The application's one socket.
 *
 * A module-level instance because in a browser tab the module and the
 * application are the same thing — there is no second application to hand a
 * second socket to, and the server keys what it pushes by user rather than by
 * connection. Opening is still lazy: nothing connects until a screen asks to
 * watch something.
 */
let socket: RealtimeSocket | null = null

function socketUrl(): string {
  const url = new URL(serverUrl("/api/v1/ws"))
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

export function realtime(): RealtimeSocket {
  socket ??= createRealtimeSocket({
    url: socketUrl(),
    // Read at connect time rather than captured: signing out and back in
    // must not reconnect with the token of whoever was here before.
    token: () => useAuthStore().token,
  })
  return socket
}

/** Drop the connection — on sign-out, when the token stops being ours. */
export function closeRealtime() {
  socket?.close()
  socket = null
}
