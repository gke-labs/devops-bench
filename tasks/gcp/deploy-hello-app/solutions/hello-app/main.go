// Package main is the HTTP-server oracle image for the deploy-hello-app task.
//
// It is the known-good, HTTP-converted counterpart to the task fixture at
// tasks/gcp/deploy-hello-app/hello-app/main.go (a fmt.Println one-shot). Step 2
// of docs/appendix/deploy-hello-app-oracle-validation.md builds and pushes this
// image; solutions/oracle.yaml points its Deployment at the pushed tag.
//
// The server listens on :8080 and returns 200 from every path, satisfying both
// the oracle's GET / readiness/liveness probes and the task's serving-http
// objective (an in-cluster http_probe expecting 200 from the Service root). It
// writes nothing to disk and needs no privileges, so it runs unchanged under
// the restricted Pod Security Standard the oracle namespace enforces
// (runAsNonRoot, readOnlyRootFilesystem, all capabilities dropped).
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "Hello from hello-app (path %q)\n", r.URL.Path)
	})

	const addr = ":8080"
	log.Printf("hello-app listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Printf("hello-app server error: %v", err)
		os.Exit(1)
	}
}
