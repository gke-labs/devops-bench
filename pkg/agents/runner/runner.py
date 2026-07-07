import os
import subprocess

def run_gcli_agent(prompt, gemini_path="gemini"):
    """Runs Gemini CLI with GKE MCP extension."""
    try:
        # Using 'gemini run' as suggested by user
        result = subprocess.run(
            [gemini_path, "-p", prompt],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"

def run_openclaw_agent(prompt, binary_path="openclaw"):
    """Runs OpenClaw agent with a prompt."""
    try:
        # Using 'openclaw agent --message' as suggested by user
        result = subprocess.run(
            [binary_path, "agent", "--message", prompt],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"

def main():
    goal = "what can you do"

    gemini_path = os.environ.get("GEMINI_PATH", "gemini")
    openclaw_path = os.environ.get("OPENCLAW_PATH", "openclaw")

    print(f"Invoking GCLI agent with goal: {goal!r}")
    output_gcli = run_gcli_agent(goal, gemini_path)
    print("--- GCLI Output ---")
    print(output_gcli)

    print(f"\nInvoking OpenClaw agent with goal: {goal!r}")
    output_openclaw = run_openclaw_agent(goal, openclaw_path)
    print("--- OpenClaw Output ---")
    print(output_openclaw)

if __name__ == "__main__":
    main()
