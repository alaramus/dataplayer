import { execFile } from "node:child_process"
import { connect } from "node:net"
import { promisify } from "node:util"
import { fileURLToPath } from "node:url"

import { test } from "@playwright/test"

import { SSH_SERVER } from "./connectors"
import { REDIS } from "./redis"

const execFileAsync = promisify(execFile)
const REPOSITORY_ROOT = fileURLToPath(new URL("../../../", import.meta.url))
const PROBE_TIMEOUT_MS = 1000
const COMPOSE_TIMEOUT_MS = 5000

type Service = "redis" | "ssh" | "metrics"

const START_COMMANDS: Record<Service, string> = {
  redis: "docker compose up -d redis",
  ssh: "docker compose up -d sshd",
  metrics: "docker compose up -d metrics",
}

/** Send a server-protocol hello and require a reply, not just an open port. */
function tcpServerAnswers(
  host: string,
  port: number,
  hello: string,
  replyStartsWith: readonly string[]
): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = connect({ host, port })
    let settled = false
    const finish = (answers: boolean) => {
      if (settled) return
      settled = true
      socket.destroy()
      resolve(answers)
    }

    socket.setTimeout(PROBE_TIMEOUT_MS, () => finish(false))
    socket.once("error", () => finish(false))
    socket.once("connect", () => socket.write(hello))
    socket.on("data", (chunk) => {
      const reply = chunk.toString()
      finish(replyStartsWith.some((prefix) => reply.startsWith(prefix)))
    })
  })
}

async function composeServiceIsRunning(service: Service): Promise<boolean> {
  try {
    const { stdout } = await execFileAsync(
      "docker",
      ["compose", "ps", "--services", "--filter", "status=running", service],
      {
        cwd: REPOSITORY_ROOT,
        encoding: "utf8",
        timeout: COMPOSE_TIMEOUT_MS,
        windowsHide: true,
      }
    )
    return stdout.split(/\r?\n/).some((line) => line.trim() === service)
  } catch {
    return false
  }
}

async function serviceAnswers(service: Service): Promise<boolean> {
  switch (service) {
    case "redis":
      return tcpServerAnswers(REDIS.host, REDIS.port, "PING\r\n", ["+", "-"])
    case "ssh":
      return tcpServerAnswers(
        "127.0.0.1",
        Number(SSH_SERVER.port),
        "SSH-2.0-dataplayer-probe\r\n",
        ["SSH-"]
      )
    case "metrics":
      // The collector receives UDP without replying. Its Compose state is the
      // availability signal for the local E2E stack.
      return composeServiceIsRunning(service)
  }
}

/** Skip a scenario when one of its optional local services is not available. */
export async function requireE2EService(service: Service): Promise<void> {
  if (await serviceAnswers(service)) return

  const details: Record<Service, string> = {
    redis: `Redis does not answer at ${REDIS.host}:${REDIS.port}`,
    ssh: `The SSH server does not answer at 127.0.0.1:${SSH_SERVER.port}`,
    metrics: "The metrics collector is not running as a Docker Compose service",
  }
  test.skip(
    true,
    `${details[service]}; start it with \`${START_COMMANDS[service]}\``
  )
}
