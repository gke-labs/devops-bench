package agents
import (
	"fmt"
	"os"
)
func main() {
	// 1. Create the agent wrapper
	// We use path relative to where we will run the command (pkg/agents)
	agent := NewDeepEvalAgent(
		"../../pkg/evaluator/evaluate.py",
		"api",
		"gemini-2.5-flash",
	)
	// 2. Set environment variables needed by evaluate.py
	os.Setenv("AGENT_TYPE", "api")
	os.Setenv("AGENT_TARGET", "gemini-2.5-flash")
	os.Setenv("PROJECT_ID", "your-gcp-project")
	os.Setenv("CLUSTER_NAME", "your-cluster-name")
	// Note: GEMINI_API_KEY must also be set in your terminal
	goal := "summarize the hypercomputer d1 app in project your-gcp-project"
	context := map[string]string{
		"project_id": "your-gcp-project",
	}
	fmt.Println("=== Executing DeepEvalAgent from Go ===")
	result, err := agent.Execute(goal, context)
	if err != nil {
		fmt.Printf("Error executing agent: %v\n", err)
		return
	}
	fmt.Println("\n=== Result received in Go ===")
	fmt.Println(result.Output)
}