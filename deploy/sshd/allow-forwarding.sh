#!/bin/sh
# The development SSH server forwards connections, so a database connection
# can be pointed through it as a tunnel (D282). The image ships with
# AllowTcpForwarding off; this runs as root before sshd starts.
sed -i 's/^AllowTcpForwarding no/AllowTcpForwarding yes/' /config/sshd/sshd_config
