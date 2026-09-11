package repository

import (
	"strings"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

var readOnlyTools = map[string]struct{}{
	"glob": {},
	"grep": {},
	"read": {},
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
// read-only bypass the authority check. Unknown tools, empty schemas, extra
// arguments, shell composition, and mutating variants require authority.
//
// This is deliberately not a publication classifier. Whether an operation is
// a push, PR creation, merge, or other publication belongs to Publication Guard.
func RequiresAuthority(action policy.Action) bool {
	if _, ok := readOnlyTools[strings.ToLower(action.Tool)]; ok {
		return false
	}
	commandValue, err := policy.Command(action)
	if err != nil {
		return true
	}
	command := strings.TrimSpace(commandValue)
	if strings.ContainsAny(command, "\n\r") {
		return true
	}
	_, ok := readOnlyCommands[command]
	return !ok
}
