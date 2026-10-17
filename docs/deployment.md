# Deploying DataPlayer

What a running installation is, what it expects from the machine in front of
it, and three ways to give it HTTPS. Setting up the installation itself —
mode, preset, secrets — is the setup's job; see the README.

## What runs

With `COMPOSE_FILE=compose.yml,compose.prod.yml` the backend serves the built
interface and the API together on one port, `APP_PORT` (8000). It speaks plain
HTTP and does not care what is in front of it: it builds no address from the
request and reads no `X-Forwarded-*` header. The one address it knows is
`FRONTEND_HOST`:

- links in e-mails point there;
- it is the only origin the API accepts calls from (CORS);
- the bundled Caddy takes its domain from it.

So `FRONTEND_HOST` is exactly what people type into the browser, scheme and
port included: `https://data.example.com`, not `data.example.com` and not the
backend's own address.

DataPlayer needs a host name of its own. Serving it under a path such as
`https://example.com/dataplayer/` is not supported: the interface and the API
both assume they are at the root.

## When HTTPS is needed

Whenever the interface is opened from anywhere but the machine it runs on.

- People type database passwords, SSH keys and AI provider keys into it. Over
  plain HTTP they cross the network as text.
- A browser treats a plain HTTP page from another machine as insecure and
  takes features away from it. DataPlayer works without them, but reading the
  clipboard from a button (the grid's Paste) is one of them; Ctrl+V still
  works.

`http://localhost:8000` on the machine itself needs nothing.

## Option 1: the bundled Caddy

For a machine with nothing in front of DataPlayer yet. Caddy obtains the
certificate from Let's Encrypt, renews it and passes WebSockets through
without configuration.

You need a domain whose DNS record points at this machine, and ports 80 and
443 open to the internet: Let's Encrypt checks the domain over port 80.

The setup does it: give it `https://data.example.com` as the address people
open and choose `caddy` when it asks who serves HTTPS, or pass
`--https caddy`. It writes the same three lines you would write by hand:

```dotenv
FRONTEND_HOST=https://data.example.com
# `https` next to whatever the preset already put here.
COMPOSE_PROFILES=cache,https
# The plain port only on this machine, so nobody goes around Caddy.
APP_PORT=127.0.0.1:8000
```

Then:

```bash
docker compose up -d
docker compose logs -f caddy
```

The log shows the certificate being obtained. The configuration is
[deploy/Caddyfile](../deploy/Caddyfile); certificates are kept in the
`dataplayer_caddy-data` volume. Running the setup again keeps the choice until
the address stops being `https://` or `own` is chosen instead.

## Option 2: a proxy you already run

When nginx, Traefik, a Caddy of your own or a cloud load balancer already holds
ports 80 and 443, choose `own` in the setup (`--https own`), so no Caddy
starts, and point that proxy at DataPlayer. Whatever the proxy, it must:

1. **Pass every path to the backend.** The interface, `/api/` and the
   WebSockets live on the same port; there is nothing to split.
2. **Upgrade WebSockets.** `/api/v1/ws` carries everything the server pushes,
   `/api/v1/terminals` the terminals. Without the upgrade the interface loads
   and then never updates, and no terminal opens.
3. **Keep idle connections for a long time.** A terminal or a socket may stay
   quiet for many minutes. nginx closes such a connection after 60 seconds by
   default.
4. **Accept uploads up to `MAX_UPLOAD_BYTES`** (100 MB by default). nginx
   refuses anything over 1 MB by default.
5. **Not buffer responses.** Downloads and long answers are streamed.

Set `FRONTEND_HOST` to the proxy's HTTPS address, and `APP_PORT` to
`127.0.0.1:8000` when the proxy runs on the same machine outside Docker.

### nginx

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    http2 on;
    server_name data.example.com;

    ssl_certificate     /etc/letsencrypt/live/data.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/data.example.com/privkey.pem;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $connection_upgrade;

        proxy_read_timeout  1h;
        proxy_send_timeout  1h;
        proxy_buffering     off;
        proxy_request_buffering off;
    }
}

server {
    listen 80;
    server_name data.example.com;
    return 301 https://$host$request_uri;
}
```

The `map` block goes in the `http` context, once per server.

### Traefik

Traefik usually discovers containers through Docker labels. Put them in a file
of your own next to `compose.yml`, say `compose.traefik.yml`:

```yaml
services:
  backend:
    labels:
      - traefik.enable=true
      - traefik.http.routers.dataplayer.rule=Host(`data.example.com`)
      - traefik.http.routers.dataplayer.entrypoints=websecure
      - traefik.http.routers.dataplayer.tls.certresolver=letsencrypt
      - traefik.http.services.dataplayer.loadbalancer.server.port=8000
    networks:
      - default
      - traefik

networks:
  traefik:
    external: true
```

and add it to `.env`:

```dotenv
COMPOSE_FILE=compose.yml,compose.prod.yml,compose.traefik.yml
FRONTEND_HOST=https://data.example.com
APP_PORT=127.0.0.1:8000
```

`traefik` is the network your Traefik container is attached to, and
`websecure` and `letsencrypt` are the entry point and the certificate
resolver its own configuration declares; use your names. Traefik upgrades
WebSockets and does not time idle ones out by default. Running the setup
again keeps a Compose file it did not add.

### Caddy of your own

```caddyfile
data.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Checking it

Open `FRONTEND_HOST` and sign in. In the browser's developer tools, under
Network, `/api/v1/ws` should answer `101 Switching Protocols` and stay open;
anything else means the WebSocket upgrade is missing. A terminal that says the
connection to the server was lost after a minute or two of quiet means the
idle timeout is too short.
