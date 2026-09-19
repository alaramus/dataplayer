import type { ServicePublic } from "@/client"
import { isWorking } from "@/features/services/jobs"

/**
 * Whether a service's container is running now.
 *
 * What the runtime reports, as the commands below read it; what the row
 * believes only when the runtime could not be asked.
 */
export function isRunning(service: Pick<ServicePublic, "state" | "container_state">): boolean {
  if (service.container_state === "unknown") return service.state === "running"
  return service.container_state === "running"
}

/** The two commands that change whether a service runs and keep its data. */
export type LifecycleCommand = "start" | "stop"

/**
 * Which of the two a service's row offers, if either.
 *
 * Read off what the runtime reports rather than what the row believes: the two
 * disagree exactly when somebody stopped or removed a container by hand (D84),
 * and the button acts on the container. A runtime that could not be asked
 * offers nothing, because the command would be refused.
 *
 * A creation that never became a connection offers neither: its container may
 * hold a password nobody knows, and starting over is its way forward.
 */
export function lifecycleCommand(
  service: Pick<ServicePublic, "state" | "container_state" | "was_connected" | "job">
): LifecycleCommand | null {
  if (isWorking(service.job)) return null
  // The server refuses a command about either (BUSY_STATES), and a row can be
  // left in one by a job that was interrupted.
  if (service.state === "creating" || service.state === "removing") return null
  if (!service.was_connected) return null
  if (service.container_state === "running") return "stop"
  if (service.container_state === "stopped") return "start"
  return null
}
