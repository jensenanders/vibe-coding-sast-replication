# CodeQL CLI bundle (CLI + query packs), pinned by release and sha256.
# Release: github.com/github/codeql-action/releases/tag/codeql-bundle-v2.27.3 (published 2026-10-20)
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS fetch
ADD --checksum=sha256:0c9e32e9fcf65be4ab8df0cf0a7bb83e64aff4099fffc5f4930e84c12a454c8b \
    https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.27.3/codeql-bundle-linux-arm64.tar.gz /tmp/bundle.tar.gz
RUN mkdir /opt/ql && tar -xzf /tmp/bundle.tar.gz -C /opt/ql

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
# Node.js is required by the TypeScript extractor (measured 2026-11-01: "Could not start Node.js")
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs=20.19.2+dfsg-1+deb13u3 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=fetch /opt/ql/codeql /opt/codeql
ENV PATH=/opt/codeql:$PATH CODEQL_ENABLE_TELEMETRY=false
ENTRYPOINT ["codeql"]
