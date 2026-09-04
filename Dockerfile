# syntax=docker/dockerfile:1
FROM golang:1.25-bookworm AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/webmcp ./cmd/webmcp

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/webmcp /webmcp
USER 65532:65532
EXPOSE 3000
ENTRYPOINT ["/webmcp"]
