/** The application shell: App, router, stores, sessions, servers, sockets, downloads, clipboard. */
export const shell = {
  leave_work: {
    title: "Leave ongoing browser work?",
    message:
      "Uploads and other work running in this browser tab will stop when switching. Jobs already owned by the server will continue there.",
    confirm: "Switch server",
  },
  default_server: "Default server",
  server_url: {
    full_http: "Enter a full HTTP or HTTPS server URL.",
    full_url: "Enter a full URL, such as https://data.example.com.",
    http_only: "Use an HTTP or HTTPS server URL.",
    no_extras: "The server URL must not contain credentials, a query or a fragment.",
    invalid_destination: "Invalid destination",
  },
  servers: {
    invalid_profile: "Enter a valid server name and HTTP(S) URL.",
    default_is_configured: "The default server is configured by this installation.",
    already_saved: "That server is already saved.",
    too_many: "Remove a saved server before adding another (maximum {n}).",
  },
}
