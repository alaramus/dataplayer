import type { DocumentView } from "@/client"

/**
 * A view holding every block and every kind of value once (D420): what the
 * kit's showcase draws and what the unit tests mount. One copy, so a kind
 * added to the contract is added to both or to neither.
 */
export const SAMPLE_VIEW: DocumentView = {
  kind: "view",
  header: {
    title: "shop-web-1",
    subtitle: { kind: "link", text: "nginx:1.27", node_id: "image:sha256:1" },
    state: { kind: "state", word: "healthy", tone: "good" },
  },
  blocks: [
    { kind: "notice", text: "This container restarted 14 times", tone: "warning" },
    {
      kind: "section",
      title: "Overview",
      blocks: [
        {
          kind: "fields",
          fields: [
            { label: "ID", value: { kind: "code", text: "4f1c2a9d0b7e" } },
            { label: "Name", value: { kind: "text", text: "shop-web-1" } },
            { label: "Created", value: { kind: "moment", value: "2026-11-20T09:30:00Z" } },
            { label: "Uptime", value: { kind: "duration", seconds: 7260 } },
            { label: "Restarts", value: { kind: "number", value: 14 } },
            { label: "CPU limit", value: { kind: "number", value: 0.5, unit: "CPUs" } },
            { label: "Memory limit", value: { kind: "bytes", value: 67_108_864 } },
            { label: "Read only", value: { kind: "boolean", value: false } },
            { label: "Health", value: { kind: "state", word: "starting", tone: "busy" } },
            { label: "Tags", value: { kind: "list", items: ["latest", "1.27", "stable"] } },
            { label: "Project", value: { kind: "link", text: "shop", node_id: "project:shop" } },
            { label: "User", value: { kind: "empty" } },
          ],
        },
      ],
    },
    {
      kind: "section",
      title: "Network",
      blocks: [
        {
          kind: "table",
          columns: ["Container port", "Host address", "Host port"],
          rows: [
            [{ kind: "text", text: "80/tcp" }, { kind: "text", text: "0.0.0.0" }, { kind: "text", text: "8080" }],
            [{ kind: "text", text: "443/tcp" }, { kind: "empty" }, { kind: "empty" }],
          ],
          omitted: 2,
        },
      ],
    },
    {
      kind: "section",
      title: "Environment",
      blocks: [
        {
          kind: "pairs",
          pairs: [
            { name: "DB_PASSWORD", value: "hunter2", sensitive: true },
            { name: "LOG_LEVEL", value: "info" },
          ],
        },
      ],
    },
    {
      kind: "section",
      title: "Labels",
      collapsed: true,
      blocks: [{ kind: "pairs", pairs: [{ name: "com.docker.compose.project", value: "shop" }] }],
    },
    { kind: "notice", text: "It was killed for running out of memory", tone: "bad" },
  ],
}
