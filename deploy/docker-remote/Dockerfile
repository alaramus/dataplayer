# A Docker daemon on "another machine" for the Docker source (D405): dockerd
# and sshd in one container, a user `dataplayer` (password `dataplayer`) in the
# `docker` group, and the daemon's socket forwardable over SSH. Privileged, as
# every Docker-in-Docker is. A test stand, never a deployment.
FROM docker:29-dind

# First match wins in sshd_config, so these go before anything Alpine ships.
# sftp-server too: the SSH connection it is reached through browses over SFTP.
RUN apk add --no-cache openssh-server openssh-sftp-server \
    && ssh-keygen -A \
    && (getent group docker || addgroup -S docker) \
    && adduser -D -s /bin/sh dataplayer \
    && addgroup dataplayer docker \
    && echo 'dataplayer:dataplayer' | chpasswd \
    && sed -i '1i PasswordAuthentication yes\nAllowTcpForwarding yes\nAllowStreamLocalForwarding yes' /etc/ssh/sshd_config

COPY entrypoint.sh /usr/local/bin/docker-remote
RUN chmod +x /usr/local/bin/docker-remote

EXPOSE 22
ENTRYPOINT ["docker-remote"]
