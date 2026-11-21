#!/bin/sh
# sshd in the background, the daemon in the foreground on its socket only:
# no TCP listener, so the one way in is the socket through SSH.
set -e
# A container restarted keeps its files: the pid files of the last run would
# stop both daemons from starting again.
rm -f /var/run/docker.pid /var/run/docker/containerd/containerd.pid /run/sshd.pid
/usr/sbin/sshd
exec dind dockerd --host=unix:///var/run/docker.sock --group=docker
