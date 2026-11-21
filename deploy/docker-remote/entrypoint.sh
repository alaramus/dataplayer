#!/bin/sh
# sshd in the background, the daemon in the foreground on its socket only:
# no TCP listener, so the one way in is the socket through SSH.
set -e
/usr/sbin/sshd
exec dind dockerd --host=unix:///var/run/docker.sock --group=docker
