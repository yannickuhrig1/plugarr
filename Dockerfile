# Image PlugArr, construite par .github/workflows/docker.yml pour amd64 et arm64.
#
# Elle sert la veille en conteneur (ROADMAP, « Une veille en continu ») : un
# service en LECTURE SEULE, pour les NAS ou personne n'ouvre de session. Elle
# ne remplace pas la console, qui tourne sur l'hote : la console cree et
# recree des conteneurs, droit qu'aucun conteneur ne doit recevoir.
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

FROM ${PYTHON_IMAGE}
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
