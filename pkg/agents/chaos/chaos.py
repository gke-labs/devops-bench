import os
import subprocess


class ChaosAgent:
  """Injects faults."""

  def inject_fault(self, spec: dict):
    action_type = spec.get("type")
    target = spec.get("target", {})

    if action_type == "generate_load":
      qps = target.get("qps", 100)
      duration = target.get("duration", "30s")
      concurrency = target.get("concurrency", 4)
      service_url = target.get("service_url")
      if not service_url:
        print("Error: service_url is required for generate_load")
        return

      try:
        # Use the locally installed fortio binary
        fortio_path = os.path.expanduser("~/go/bin/fortio")
        cmd = [
            fortio_path,
            "load",
            "-qps",
            str(qps),
            "-t",
            duration,
            "-c",
            str(concurrency),
            service_url,
        ]
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        print("--- Fortio Stdout ---")
        print(result.stdout)
        print("--- Fortio Stderr ---")
        print(result.stderr)
        print(f"Successfully generated load on {service_url} with QPS {qps}")
      except subprocess.CalledProcessError as e:
        print(f"Error running fortio: {e.stderr}")
