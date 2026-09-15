package vendor

import (
	"strings"
	"testing"

	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
)

func TestParsePreToolUse(t *testing.T) {
	in, err := Parse([]byte(`{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"},"cwd":"/workspace","session_id":"s6"}`))
	if err != nil {
		t.Fatal(err)
	}
	if in.Event != PreToolUse || in.Tool != "Bash" || in.CWD != "/workspace" || in.SessionID != "s6" {
		t.Fatalf("%+v", in)
	}
	if in.Action().Tool != "Bash" {
		t.Fatal("action normalization failed")
	}
}

func TestParseStopPreservesFollowUpMarker(t *testing.T) {
	in, err := Parse([]byte(`{"hook_event_name":"Stop","cwd":"/workspace","stop_hook_active":true}`))
	if err != nil {
		t.Fatal(err)
	}
	if in.Event != Stop || !in.CompletionRequest().FollowUp {
		t.Fatalf("%+v", in)
	}
}

func TestParseUnknownEventFailsClosed(t *testing.T) {
	if _, err := Parse([]byte(`{"hook_event_name":"FutureEvent","cwd":"/workspace"}`)); err == nil {
		t.Fatal("unknown event accepted")
	}
}

func TestClaudePreservesAsk(t *testing.T) {
	r, err := MapPreTool(Claude, policy.Result("ask", "approval", "cloud"))
	if err != nil {
		t.Fatal(err)
	}
	if r.Decision != "ask" {
		t.Fatalf("%+v", r)
	}
}

func TestCodexMapsAskToDeny(t *testing.T) {
	r, err := MapPreTool(Codex, policy.Result("ask", "approval", "cloud"))
	if err != nil {
		t.Fatal(err)
	}
	if r.Decision != "deny" {
		t.Fatalf("%+v", r)
	}
}

func TestDevinMapsNonAllowToBlock(t *testing.T) {
	r, err := MapPreTool(Devin, policy.Result("deny", "force push", "force"))
	if err != nil {
		t.Fatal(err)
	}
	if r.Decision != "block" {
		t.Fatalf("%+v", r)
	}
}

func TestStopBlocksReviewRequired(t *testing.T) {
	result := completion.Result{
		Outcome: completion.OutcomeReviewRequired,
		Reason:  "agent review required",
		Evidence: completion.Evidence{
			Repository: "acme/widget",
			Checks:     []completion.Check{{Name: "deterministic_gate", Status: "pass", Detail: "tests passed"}},
		},
	}
	r, err := MapStop(Claude, result)
	if err != nil {
		t.Fatal(err)
	}
	if !r.Block || !strings.Contains(r.Reason, "completion_evidence=") || !strings.Contains(r.Reason, "tests passed") {
		t.Fatalf("%+v", r)
	}
}

func TestStopPreservesBoundedFailureEvidence(t *testing.T) {
	result := completion.Result{
		Outcome:  completion.OutcomeBlocked,
		Reason:   "deterministic completion gate failed",
		Evidence: completion.Evidence{Checks: []completion.Check{{Name: "deterministic_gate", Status: "fail", Detail: "CI failed: " + strings.Repeat("x", 8192)}}},
	}
	r, err := MapStop(Codex, result)
	if err != nil {
		t.Fatal(err)
	}
	if !r.Block || !strings.Contains(r.Reason, "CI failed") || len([]rune(r.Reason)) > maxCompletionFeedbackRunes {
		t.Fatalf("length=%d response=%+v", len([]rune(r.Reason)), r)
	}
}

func TestStopAllowsOnlyComplete(t *testing.T) {
	for _, v := range []Name{Claude, Codex, Devin} {
		r, err := MapStop(v, completion.Result{Outcome: completion.OutcomeComplete, Reason: "done"})
		if err != nil {
			t.Fatal(err)
		}
		if r.Block {
			t.Fatalf("%s %+v", v, r)
		}
	}
}

func TestUnknownDecisionFailsSafe(t *testing.T) {
	r, err := MapPreTool(Claude, policy.Decision{Decision: "future", Reason: "unknown"})
	if err != nil {
		t.Fatal(err)
	}
	if r.Decision != "deny" {
		t.Fatalf("%+v", r)
	}
}
