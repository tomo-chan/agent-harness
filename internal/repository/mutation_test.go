package repository

import (
	"testing"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

func TestRequiresAuthorityUsesPositiveReadOnlyClassification(t *testing.T) {
	for _, action := range []policy.Action{
		{Tool: "Read"},
		{Tool: "grep"},
		{Tool: "exec", Input: map[string]any{"command": "git status"}},
		{Tool: "Bash", Input: map[string]any{"command": "git branch --show-current"}},
	} {
		if RequiresAuthority(action) {
			t.Errorf("read-only action required mutation authority: %+v", action)
		}
	}
	for _, action := range []policy.Action{
		{Tool: "Write"},
		{Tool: "exec", Input: map[string]any{"command": "git branch -D feature/x"}},
		{Tool: "exec", Input: map[string]any{"command": "find . -delete"}},
		{Tool: "exec", Input: map[string]any{"command": "git status --short"}},
		{Tool: "exec", Input: map[string]any{"command": "git status && touch changed"}},
		{Tool: "mcp_delete"},
		{Tool: "unknown"},
	} {
		if !RequiresAuthority(action) {
			t.Errorf("mutation bypassed authority: %+v", action)
		}
	}
}
