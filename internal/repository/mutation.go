package repository

import (
	"strings"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

var readOnlyTools = map[string]struct{}{
	"Glob": {},
	"Grep": {},
	"Read": {},
}

var shellTools = map[string]struct{}{
	"Bash": {},
	"exec": {},
}

var readOnlyCommands = map[string]struct{}{
	"git branch --show-current":     {},
	"git diff":                      {},
	"git log":                       {},
	"git rev-parse --show-toplevel": {},
	"git status":                    {},
	"git worktree list":             {},
	"pwd":                           {},
}

// RequiresAuthority conservatively identifies operations that may mutate a
// repository. Only fixed adapter tools and exact command forms known to be
// read-only bypass the authority check. Command forms apply only to recognized
// shell tools. Unknown tools, empty schemas, extra arguments, shell composition,
// and mutating variants require authority. Deployment must still bind the fixed
// read-only tool names to adapter capabilities; raw model claims are not trust.
//
// This is deliberately not a publication classifier. Whether an operation is
// a push, PR creation, merge, or other publication belongs to Publication Guard.
func RequiresAuthority(action policy.Action) bool {
	commandValue, err := policy.Command(action)
	if err != nil {
		return true
	}
	if _, ok := readOnlyTools[action.Tool]; ok && strings.TrimSpace(commandValue) == "" {
		return false
	}
	if _, ok := shellTools[action.Tool]; !ok {
		return true
	}
	command := strings.TrimSpace(commandValue)
	if strings.ContainsAny(command, "\n\r") {
		return true
	}
	_, ok := readOnlyCommands[command]
	return !ok
}
