# Image PlugArr, construite par .github/workflows/docker.yml pour amd64 et arm64.
#
# DEUX cibles, et la difference n'est pas un detail d'empaquetage :
#
# - par defaut, l'image de la VEILLE : un service en LECTURE SEULE, sans aucun
#   client Docker. Meme si on lui tendait le socket, elle ne saurait pas s'en
#   servir. C'est elle que le compose installe ;
# - `--target admin`, publiee sous un tag distinct : la console, avec le client
#   Docker et le greffon compose. Elle cree, demarre et recree des conteneurs,
#   donc elle exige le socket, et un conteneur qui peut creer des conteneurs
#   peut monter la racine de l'hote et tourner en root. C'est un choix explicite
#   pour les machines sans systemd, pas le chemin recommande : sur un Linux, la
#   console tourne sur l'hote et demarre avec `plugarr autostart --systeme`.
#
# Base epinglee par tag complet ET condensat de l'index multi-architecture,
# comme le reste du catalogue : deux constructions du meme commit partent de
# la meme image.
ARG PYTHON_IMAGE=python:3.12.14-slim-trixie@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

FROM ${PYTHON_IMAGE} AS construction
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /roues .

FROM ${PYTHON_IMAGE} AS execution
# Un compte sans privilege. `user:` dans le compose le remplace par PUID:PGID,
# comme pour Seerr, pour lire les dossiers de l'installation.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin plugarr
COPY --from=construction /roues /roues
RUN pip install --no-cache-dir /roues/*.whl && rm -rf /roues
USER plugarr
WORKDIR /home/plugarr
ENV PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.source="https://github.com/yannickuhrig1/plugarr" \
      org.opencontainers.image.description="PlugArr : deploie et cable une stack media *arr" \
      org.opencontainers.image.licenses="MIT"
ENTRYPOINT ["plugarr"]
CMD ["--help"]

# ---------------------------------------------------------------- admin
#
# Variante pour la CONSOLE en conteneur, publiee sous un tag distinct. Elle
# ajoute le client Docker et le greffon compose, que la console appelle pour
# demarrer, arreter et recreer des services.
#
# Ce que cette variante suppose est enorme, et c'est voulu qu'elle soit a part :
# avec le socket, elle peut tout faire sur la machine. L'image de la VEILLE, qui
# n'a rien a piloter, ne contient donc aucun client Docker — elle ne saurait
# meme pas s'en servir si on lui tendait le socket.
#
# Depuis le depot apt de Docker, signe, versions epinglees : le binaire statique
# aurait demande de figer un condensat par architecture a la main.
FROM execution AS admin
ARG DOCKER_CLI="5:29.8.1-1~debian.13~trixie"
ARG COMPOSE_PLUGIN="5.5.1-1~debian.13~trixie"
USER root
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
    gpg --show-keys --with-colons /etc/apt/keyrings/docker.gpg \
        | grep -q '9DC858229FC7DD38854AE2D88D81803C0EBFCD88'; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian trixie stable" > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "docker-ce-cli=${DOCKER_CLI}" "docker-compose-plugin=${COMPOSE_PLUGIN}"; \
    apt-get purge -y gnupg; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*; \
    docker --version; \
    docker compose version
USER plugarr

# La derniere etape est celle que `docker build` prend par defaut : l'image
# ordinaire, sans client Docker. La variante admin se demande explicitement,
# par `--target admin`.
FROM execution AS veille
