# SSH system reports

## D266. SSH reports connection and filesystem facts through SSH and SFTP

Put a `System` section before an SSH source's remote files. Its read-only
`Connection` report combines the saved connection options with the current
authenticated session: the pinned server key's algorithm and fingerprint,
server banner, negotiated SSH cipher/MAC/compression, SFTP version and remote
copy support when those facts are available. It never shows a password, a
private key, or the pinned key's public material.

The `Filesystem` report asks SFTP for `statvfs` at the folder where the
catalog starts. It shows total, free and available bytes and inode counts when
the server reports them, and a clear unavailable value when it does not.

Both reports reuse the authenticated connection and issue no shell commands.
That preserves D144: the terminal is the only way a command runs on the remote
server, and the person types into it.
