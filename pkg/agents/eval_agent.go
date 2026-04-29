package agents

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"os/exec"
)

type DeepEvalAgent struct {
	scriptPath  string // Path to test_agent.py
	agentType   string // 'cli', 'api', or 'mcp'
	agentTarget string // path to binary or server address
}

func NewDeepEvalAgent(scriptPath, agentType, agentTarget string) *DeepEvalAgent {
	return &DeepEvalAgent{
		scriptPath:  scriptPath,
		agentType:   agentType,
		agentTarget: agentTarget,
	}
}

func (a *DeepEvalAgent) Name() string { return "DeepEval Agent Wrapper" }

func (a *DeepEvalAgent) Execute(goal string, context map[string]string) (ExecutionResult, error) {
	// 1. Prepare data for Python
	evalData := map[string]interface{}{
		"goal":    goal,
		"context": context,
	}
	jsonData, _ := json.MarshalIndent(evalData, "", "  ")
	tmpFile := "devops_eval_data.json"
	ioutil.WriteFile(tmpFile, jsonData, 0644)
	defer os.Remove(tmpFile)

	// 2. Invoke Python script
	cmd := exec.Command("python3", a.scriptPath, tmpFile)
	
	// Pass agent configuration via environment variables
	cmd.Env = append(os.Environ(),
		"AGENT_TYPE="+a.agentType,
		"AGENT_TARGET="+a.agentTarget,
	)
	
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		return ExecutionResult{}, fmt.Errorf("failed to run test_agent.py: %w, stderr: %s", err, stderr.String())
	}

	// 3. Return the JSON output from Python in the ExecutionResult
	return ExecutionResult{
		Output: stdout.String(),
	}, nil
}
