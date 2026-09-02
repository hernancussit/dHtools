FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates git openssh-client && \
    rm -rf /var/lib/apt/lists/*



# Deno: motor de JavaScript que yt-dlp necesita para resolver los desafíos
# que YouTube exige antes de entregar los links reales de video/audio.
ENV DENO_INSTALL=/usr/local
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y
ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install -U --pre yt-dlp[default]

COPY . .
RUN mkdir -p /app/downloads

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "600", "app:app"]
