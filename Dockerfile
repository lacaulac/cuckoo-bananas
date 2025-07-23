FROM ghcr.io/astral-sh/uv:alpine3.21
ADD . /app
WORKDIR /app
RUN apk add --no-cache ffmpeg git
CMD uv run main.py