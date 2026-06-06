from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import base64
import os

ETCD_ENDPOINT = "http://etcd-headless:2379"

def check_etcd_health():
    try:
        req = urllib.request.Request(f"{ETCD_ENDPOINT}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data.get("health") == "true" or data.get("health") is True:
                return True
    except Exception as e:
        print(f"Error checking etcd health: {e}")
    return False

def read_config_value(config_map_name, key):
    path = f"/config/{config_map_name}/{key}"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading {path}: {e}")
    return None

class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            if check_etcd_health():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Healthy"}).encode())
            else:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Unhealthy", "reason": "etcd quorum lost"}).encode())
        
        elif self.path == "/api/v1/status":
            status = read_config_value("control-plane-status", "status") or "Healthy"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": status}).encode())

        elif self.path == "/api/v1/workloads":
            # "/workloads/" in base64: L3dvcmtsb2Fkcy8=
            # "/workloads0" in base64: L3dvcmtsb2FkczA=
            payload = {
                "key": base64.b64encode(b"/workloads/").decode(),
                "range_end": base64.b64encode(b"/workloads0").decode()
            }
            try:
                req = urllib.request.Request(
                    f"{ETCD_ENDPOINT}/v3/kv/range",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    res_data = json.loads(response.read().decode())
                    kvs = res_data.get("kvs", [])
                    workloads = []
                    for kv in kvs:
                        key = base64.b64decode(kv.get("key", "")).decode()
                        val = base64.b64decode(kv.get("value", "")).decode()
                        workloads.append({"name": key.replace("/workloads/", ""), "image": val})
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(workloads).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/v1/workloads":
            block_mutations = read_config_value("control-plane-config", "block-mutating-requests")
            if block_mutations == "true":
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Mutating requests are blocked due to control plane degradation"}).encode())
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode())
                name = data.get("name")
                image = data.get("image")
                if not name or not image:
                    self.send_response(400)
                    self.end_headers()
                    return

                key_b64 = base64.b64encode(f"/workloads/{name}".encode()).decode()
                val_b64 = base64.b64encode(image.encode()).decode()
                payload = {"key": key_b64, "value": val_b64}

                req = urllib.request.Request(
                    f"{ETCD_ENDPOINT}/v3/kv/put",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    self.send_response(201)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "Created"}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), APIHandler)
    print("Starting mock apiserver on port 8080...")
    server.serve_forever()
