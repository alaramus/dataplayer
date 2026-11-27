#!/bin/sh
# The development SSH server forwards connections, so a database connection
# can be pointed through it as a tunnel (D282). The image ships with
# AllowTcpForwarding off; this runs as root before sshd starts.
sed -i 's/^AllowTcpForwarding no/AllowTcpForwarding yes/' /config/sshd/sshd_config
# OpenSSH 9.8 and later refuse an address for a while after connections that
# leave without signing in or fail to. The tests make many of both — a probe
# before every test, sign-ins meant to fail — and the server then closed every
# connection from the runner for the rest of the suite.
grep -q '^PerSourcePenalties' /config/sshd/sshd_config \
  || echo 'PerSourcePenalties no' >> /config/sshd/sshd_config
