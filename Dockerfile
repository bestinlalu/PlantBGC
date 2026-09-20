FROM ubuntu:24.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# ubuntu:24.04 provides sendmail 8.18.1 — same version as the host VM — so the
# bind-mounted sendmail.cf and gmail-auth.db are version-compatible.
# sasl2-bin and sendmail installed together (installing separately requires dpkg-reconfigure)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    ca-certificates \
    sasl2-bin \
    libsasl2-modules \
    sendmail \
    && rm -f /usr/lib/python3*/EXTERNALLY-MANAGED \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/mail/authinfo && chmod 700 /etc/mail/authinfo

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

COPY plantbgc-service /app/plantbgc-service

ENV PYTHONPATH="/app/plantbgc-service:${PYTHONPATH}"

EXPOSE 8000
