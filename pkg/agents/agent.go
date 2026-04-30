package agents

// ExecutionResult holds the result of an agent execution.
type ExecutionResult struct {
	Output string
}

// DevOpsAgent defines the interface for DevOps agents.
type DevOpsAgent interface {
	Name() string
	Execute(goal string, context map[string]string) (ExecutionResult, error)
}