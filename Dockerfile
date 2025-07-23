FROM ghcr.io/astral-sh/uv:alpine3.21
ADD . /app
WORKDIR /app
RUN apk add --no-cache ffmpeg git opus-dev
CMD uv run main.py