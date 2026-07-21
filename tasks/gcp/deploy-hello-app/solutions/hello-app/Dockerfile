# Multi-stage build for the deploy-hello-app oracle image.
#
# Produces a static, non-root container that listens on :8080 and returns 200,
# matching solutions/oracle.yaml (container port 8080 named "http", GET /
# probes) and the restricted Pod Security Standard the oracle namespace
# enforces. See docs/appendix/deploy-hello-app-oracle-validation.md Step 2 for
# the build-and-push commands. Build for linux/amd64 to match GKE nodes.

FROM golang:1.23-bookworm AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
# CGO off => a fully static binary that runs on the distroless static base and
# under readOnlyRootFilesystem with no runtime libc dependency.
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/hello-app .

# distroless static + nonroot: no shell, no package manager, unprivileged user
# by default. The oracle pod further pins runAsUser 1000 / runAsNonRoot /
# readOnlyRootFilesystem, all of which this image satisfies.
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/hello-app /hello-app
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/hello-app"]
