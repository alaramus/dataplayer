import { connect } from "node:net"

/**
 * The development Redis as the scenarios reach it: `redis` from
 * compose.override.yml, published on this machine's 6379 and asking for no
 * password. A connection made in a scenario names the host the backend
 * container sees; the keys a scenario starts from are written from here.
 *
 * Its own database, so a scenario that empties it empties nothing else.
 */
export const REDIS = {
  host: process.env.E2E_REDIS_HOST ?? "localhost",
  port: Number(process.env.E2E_REDIS_PORT ?? "6379"),
  serverHost: "redis",
  database: 14,
}

function encoded(command: string[]): string {
  return `*${String(command.length)}\r\n${command
    .map((part) => `$${String(Buffer.byteLength(part))}\r\n${part}\r\n`)
    .join("")}`
}

/**
 * Run commands in the scenarios' database, in order, and wait for the server
 * to have answered them all. Plain RESP over a socket: one helper is not worth
 * a client library.
 */
export async function redisCommands(commands: string[][]): Promise<void> {
  const all = [["SELECT", String(REDIS.database)], ...commands, ["QUIT"]]
  await new Promise<void>((resolve, reject) => {
    const socket = connect(REDIS.port, REDIS.host, () => {
      socket.write(all.map(encoded).join(""))
    })
    let answered = ""
    socket.on("data", (chunk) => {
      answered += chunk.toString()
    })
    socket.on("error", reject)
    socket.on("close", () => {
      const refused = answered.split("\r\n").find((line) => line.startsWith("-"))
      if (refused === undefined) resolve()
      else reject(new Error(`Redis refused a command: ${refused}`))
    })
  })
}
