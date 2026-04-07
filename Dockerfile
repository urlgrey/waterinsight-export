FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/skidder/waterinsight-export"

RUN groupadd -r app && useradd -r -g app -d /app app
COPY --from=builder /install /usr/local
COPY src/ /app/src/

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

VOLUME /data
USER app

ENTRYPOINT ["python", "-m", "watersight_export.main"]
CMD ["--daemon"]
