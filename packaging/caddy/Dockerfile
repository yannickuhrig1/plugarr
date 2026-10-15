# Caddy avec le module caddy-dns/cloudflare, pour l'acces HTTPS prive par
# DNS-01 (docs/PLAN_HTTPS_DNS01.md). Construite par
# .github/workflows/caddy.yml pour amd64 et arm64, publiee a la demande.
#
# L'image officielle n'embarque que les modules standard : sans celui-ci,
# Caddy ne sait pas poser chez Cloudflare l'enregistrement TXT du defi DNS-01,
# et le certificat wildcard est impossible.
#
# Les deux versions donnent le tag publie, `<caddy>-cloudflare-<module>` :
# changer l'une, c'est publier une autre image. CADDY_RELEASE doit rester celle
# des deux images de base, le workflow le verifie.
ARG CADDY_RELEASE=v2.11.4
ARG CLOUDFLARE_RELEASE=v0.2.4

# Bases epinglees par tag complet ET condensat de l'index multi-architecture,
# comme le reste du catalogue. Releves sur Docker Hub le 2026-10-15.
ARG BUILDER_IMAGE=caddy:2.11.4-builder@sha256:369218c81ca6d6af249981221b3a5c764d886dd5b058f51d144066de13f2418d
ARG RUNTIME_IMAGE=caddy:2.11.4-alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b

# Compilation sur l'architecture de la machine qui construit, pour la cible
# demandee : Go compile en croise sans emulation, la ou xcaddy sous QEMU
# prendrait de longues minutes pour arm64.
FROM --platform=$BUILDPLATFORM ${BUILDER_IMAGE} AS construction
ARG CADDY_RELEASE
ARG CLOUDFLARE_RELEASE
ARG TARGETOS
ARG TARGETARCH
# La capacite est posee dans l'image finale : un COPY entre etapes ne garantit
# pas de la conserver.
ENV XCADDY_SETCAP=0
RUN GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" CGO_ENABLED=0 \
    xcaddy build "${CADDY_RELEASE}" \
        --with "github.com/caddy-dns/cloudflare@${CLOUDFLARE_RELEASE}" \
        --output /caddy

# L'image officielle, dont seul le binaire change : memes dossiers, memes
# variables XDG, meme commande par defaut. La passerelle s'utilise donc comme
# l'image `caddy` que PlugArr epingle deja.
FROM ${RUNTIME_IMAGE}
ARG CADDY_RELEASE
ARG CLOUDFLARE_RELEASE
COPY --from=construction /caddy /usr/bin/caddy
# Meme droit que le binaire officiel qu'il remplace : ecouter 443 sans root.
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy && caddy version
LABEL org.opencontainers.image.title="plugarr-caddy" \
      org.opencontainers.image.version="${CADDY_RELEASE}-cloudflare-${CLOUDFLARE_RELEASE}" \
      org.opencontainers.image.description="Caddy avec caddy-dns/cloudflare, passerelle HTTPS privee de PlugArr" \
      org.opencontainers.image.source="https://github.com/yannickuhrig1/plugarr" \
      org.opencontainers.image.licenses="Apache-2.0"
