"""The Docker Engine API, spoken over whatever transport a caller hands in (D406).

Not a source type: the pieces both the managed services (over this server's
own socket) and the Docker source (over a socket forwarded through SSH) need,
so the API has one client. What each side asks the daemon for stays its own.
"""
