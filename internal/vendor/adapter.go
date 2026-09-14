package vendor

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
)

type Name string

const (
	Claude Name = "claude"
	Codex  Name = "codex"
	Devin  Name = "devin"
)

type Event string

const (
	SessionStart Event = "SessionStart"
	PreToolUse   Event = "PreToolUse"
	Stop         Event = "Stop"
)

type Input struct {
	Event          Event
	Tool           string
	ToolInput      map[string]any
	CWD            string
	SessionID      string
	StopHookActive bool
}

// Parse normalizes the shared hook fields used by the existing vendor adapters.
// Vendor-specific opaque fields are not interpreted as authority.
func Parse(raw []byte) (Input, error) {
	var value map[string]any
	if err := json.Unmarshal(raw, &value); err != nil { return Input{}, fmt.Errorf("invalid hook input: %w", err) }
	out := Input{Event: PreToolUse}
	if v, ok := value["hook_event_name"]; ok {
		s, ok := v.(string); if !ok { return Input{}, fmt.Errorf("invalid hook_event_name") }
		out.Event = Event(s)
	}
	switch out.Event { case SessionStart, PreToolUse, Stop: default: return Input{}, fmt.Errorf("unsupported hook event %q", out.Event) }
	if v, ok := value["cwd"]; ok { s,ok:=v.(string); if !ok||strings.TrimSpace(s)=="" {return Input{},fmt.Errorf("invalid cwd")}; out.CWD=s }
	if v, ok := value["session_id"]; ok { s,ok:=v.(string); if !ok{return Input{},fmt.Errorf("invalid session_id")}; out.SessionID=s }
	if v, ok := value["stop_hook_active"]; ok { b,ok:=v.(bool); if !ok{return Input{},fmt.Errorf("invalid stop_hook_active")}; out.StopHookActive=b }
	if out.Event==PreToolUse {
		tool,ok:=value["tool_name"].(string); if !ok||strings.TrimSpace(tool)=="" { return Input{},fmt.Errorf("missing tool_name") }
		input,ok:=value["tool_input"].(map[string]any); if !ok { return Input{},fmt.Errorf("missing tool_input") }
		out.Tool=tool; out.ToolInput=input
	}
	if out.Event!=SessionStart && strings.TrimSpace(out.CWD)=="" { return Input{},fmt.Errorf("cwd is required") }
	return out,nil
}

func (i Input) Action() policy.Action { return policy.Action{Tool:i.Tool,Input:i.ToolInput,CWD:i.CWD} }
func (i Input) CompletionRequest() completion.Request { return completion.Request{CWD:i.CWD,FollowUp:i.StopHookActive} }

type PreToolResponse struct { Decision string `json:"decision"`; Reason string `json:"reason"` }

type StopResponse struct { Block bool `json:"block"`; Reason string `json:"reason,omitempty"` }

// MapPreTool preserves native ask only where the current adapter contract supports it.
// Codex maps ask to deny, while Devin represents non-allow as block externally.
func MapPreTool(v Name, d policy.Decision) (PreToolResponse,error) {
	decision:=d.Decision
	if decision!="allow"&&decision!="ask"&&decision!="deny" { decision="deny" }
	reason:=d.Reason
	switch v {
	case Claude:
		return PreToolResponse{Decision:decision,Reason:reason},nil
	case Codex:
		if decision=="ask" { return PreToolResponse{Decision:"deny",Reason:"approval required; Codex ask is mapped to deny: "+reason},nil }
		return PreToolResponse{Decision:decision,Reason:reason},nil
	case Devin:
		if decision=="allow" { return PreToolResponse{Decision:"allow",Reason:reason},nil }
		prefix:=""; if decision=="ask" {prefix="approval required: "}
		return PreToolResponse{Decision:"block",Reason:prefix+reason},nil
	default:
		return PreToolResponse{},fmt.Errorf("unsupported vendor %q",v)
	}
}

func MapStop(v Name, r completion.Result) (StopResponse,error) {
	switch v {case Claude,Codex,Devin: default:return StopResponse{},fmt.Errorf("unsupported vendor %q",v)}
	if r.Outcome==completion.OutcomeComplete { return StopResponse{},nil }
	return StopResponse{Block:true,Reason:r.Reason},nil
}
