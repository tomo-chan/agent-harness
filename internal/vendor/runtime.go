package vendor

import (
	"encoding/json"
	"fmt"

	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
)

type PreToolEvaluator interface {
	Evaluate(policy.Action) (policy.Decision, error)
}

type CompletionEvaluator interface {
	Evaluate(completion.Request) (completion.Result, error)
}

type SessionContextProvider interface {
	Context(string) (string, error)
}

type Dependencies struct {
	PreTool    PreToolEvaluator
	Completion CompletionEvaluator
	Session    SessionContextProvider
}

func failClosed(v Name, reason string) map[string]any {
	switch v {
	case Claude, Codex:
		return map[string]any{"hookSpecificOutput": map[string]any{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":reason}}
	case Devin:
		return map[string]any{"decision":"block","reason":reason}
	default:
		return map[string]any{"decision":"block","reason":reason}
	}
}

// Handle maps a vendor lifecycle payload into the common S1-S5 contracts and
// renders the currently supported vendor response shape. Dependencies must be
// supplied from the trusted runtime; repository input cannot select them.
func Handle(v Name, raw []byte, deps Dependencies) (map[string]any, error) {
	if v != Claude && v != Codex && v != Devin { return failClosed(v,"unsupported vendor"), fmt.Errorf("unsupported vendor %q",v) }
	in, err := Parse(raw)
	if err != nil { return failClosed(v,err.Error()), err }
	switch in.Event {
	case SessionStart:
		if deps.Session == nil { return failClosed(v,"session context provider unavailable"), fmt.Errorf("session provider unavailable") }
		ctx, err := deps.Session.Context(in.CWD); if err != nil { return failClosed(v,"session context unavailable"), err }
		return map[string]any{"hookSpecificOutput":map[string]any{"hookEventName":"SessionStart","additionalContext":ctx}},nil
	case PreToolUse:
		if deps.PreTool == nil { return failClosed(v,"pre-tool evaluator unavailable"), fmt.Errorf("pre-tool evaluator unavailable") }
		d, err := deps.PreTool.Evaluate(in.Action()); if err != nil { return failClosed(v,"pre-tool evaluation failed"), err }
		mapped, err := MapPreTool(v,d); if err != nil { return failClosed(v,err.Error()),err }
		switch v {
		case Claude, Codex:
			return map[string]any{"hookSpecificOutput":map[string]any{"hookEventName":"PreToolUse","permissionDecision":mapped.Decision,"permissionDecisionReason":mapped.Reason}},nil
		case Devin:
			if mapped.Decision=="allow" { return map[string]any{},nil }
			return map[string]any{"decision":"block","reason":mapped.Reason},nil
		}
	case Stop:
		if deps.Completion == nil { return failClosed(v,"completion evaluator unavailable"), fmt.Errorf("completion evaluator unavailable") }
		r, err := deps.Completion.Evaluate(in.CompletionRequest()); if err != nil { return map[string]any{"decision":"block","reason":"completion evaluation failed"},err }
		mapped, err := MapStop(v,r); if err != nil { return failClosed(v,err.Error()),err }
		if !mapped.Block { return map[string]any{},nil }
		return map[string]any{"decision":"block","reason":mapped.Reason},nil
	}
	return failClosed(v,"unsupported event"),fmt.Errorf("unsupported event")
}

func EncodeResponse(value map[string]any) ([]byte,error) { return json.Marshal(value) }
