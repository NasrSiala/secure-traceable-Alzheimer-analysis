#!/usr/bin/env sh
# Préparer les clés dans un tmpfs privé sans modifier le wallet hôte.
set -eu

if [ "$(id -u)" = 0 ]; then
    : "${WALLET_SOURCE:?Wallet source requis}"
    : "${WALLET_DIR:?Wallet temporaire requis}"
    umask 077
    mkdir -p "$WALLET_DIR"
    cp -a "$WALLET_SOURCE/." "$WALLET_DIR/"
    chown -R node:node "$WALLET_DIR"
    chmod -R u=rwX,go= "$WALLET_DIR"
    exec setpriv --reuid=node --regid=node --init-groups \
        --inh-caps=-all --bounding-set=-all node dist/server.js
fi

exec node dist/server.js
