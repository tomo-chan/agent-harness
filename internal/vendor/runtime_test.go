package vendor

import (
	"errors"
	"testing"

	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
)

type pretoolStub struct { d policy.Decision; err error }
func (s pretoolStub) Evaluate(policy.Action)(policy.Decision,error){return s.d,s.err}
type completionStub struct { r completion.Result; err error }
func (s completionStub) Evaluate(completion.Request)(completion.Result,error){return s.r,s.err}
type sessionStub struct { value string; err error }
func (s sessionStub) Context(string)(string,error){return s.value,s.err}

func TestHandleClaudePreToolAsk(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"terraform plan"},"cwd":"/workspace"}`)
	out,err:=Handle(Claude,raw,Dependencies{PreTool:pretoolStub{d:policy.Result("ask","approval","cloud")}});if err!=nil{t.Fatal(err)}
	hs:=out["hookSpecificOutput"].(map[string]any);if hs["permissionDecision"]!="ask"{t.Fatalf("%+v",out)}
}

func TestHandleCodexAskDoesNotEscalateToAllow(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"terraform plan"},"cwd":"/workspace"}`)
	out,err:=Handle(Codex,raw,Dependencies{PreTool:pretoolStub{d:policy.Result("ask","approval","cloud")}});if err!=nil{t.Fatal(err)}
	hs:=out["hookSpecificOutput"].(map[string]any);if hs["permissionDecision"]!="deny"{t.Fatalf("%+v",out)}
}

func TestHandleStopReviewRequiredBlocks(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"Stop","cwd":"/workspace","stop_hook_active":false}`)
	out,err:=Handle(Claude,raw,Dependencies{Completion:completionStub{r:completion.Result{Outcome:completion.OutcomeReviewRequired,Reason:"review required"}}});if err!=nil{t.Fatal(err)}
	if out["decision"]!="block"{t.Fatalf("%+v",out)}
}

func TestHandleFollowUpCompleteAllows(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"Stop","cwd":"/workspace","stop_hook_active":true}`)
	out,err:=Handle(Devin,raw,Dependencies{Completion:completionStub{r:completion.Result{Outcome:completion.OutcomeComplete,Reason:"done"}}});if err!=nil{t.Fatal(err)}
	if len(out)!=0{t.Fatalf("%+v",out)}
}

func TestHandleEvaluatorFailureFailsClosed(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"},"cwd":"/workspace"}`)
	out,err:=Handle(Devin,raw,Dependencies{PreTool:pretoolStub{err:errors.New("boom")}});if err==nil{t.Fatal("expected error")};if out["decision"]!="block"{t.Fatalf("%+v",out)}
}

func TestHandleSessionContext(t *testing.T){
	raw:=[]byte(`{"hook_event_name":"SessionStart","cwd":"/workspace"}`)
	out,err:=Handle(Claude,raw,Dependencies{Session:sessionStub{value:"shared-context"}});if err!=nil{t.Fatal(err)}
	hs:=out["hookSpecificOutput"].(map[string]any);if hs["additionalContext"]!="shared-context"{t.Fatalf("%+v",out)}
}
