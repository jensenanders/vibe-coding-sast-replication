# Pinned base image (digest checked 2026-10-31; Python 3.12.16, Debian 13.7)
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

# git for blobless clones in `screen` (version pinned, checked 2026-11-01).
# `scan` (added 2026-11-01): cloc counts lines here; docker-cli starts the pinned
# GitLab SAST and CodeQL images through the host's Docker (socket mounted in compose).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git=1:2.47.3-0+deb13u1 ca-certificates \
      cloc=2.04-1 docker-cli=26.1.5+dfsg1-9+deb13u1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY src /app/src
COPY tests /app/tests
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_TERMINAL_PROMPT=0

ENTRYPOINT ["python", "-m", "msrpipe"]
