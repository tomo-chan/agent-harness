package repository

import (
	"context"
	"time"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

// AssessCompletion establishes fresh read-only repository identity and posture
// at Stop. It preserves task/worktree/branch bindings but does not apply direct
// mutation-target or protected-branch prohibitions, and never grants mutation
// authority to the caller.
func AssessCompletion(ctx context.Context, cwd string, config *Config, git Git, github GitHub, now time.Time) (Report, error) {
	action := policy.Action{Tool: "Completion", Input: map[string]any{}, CWD: cwd}
	return assess(ctx, action, config, git, github, now, assessmentCompletion)
}
