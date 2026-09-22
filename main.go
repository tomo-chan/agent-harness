// agent-harness is the trusted Agent Harness binary. With no subcommand it
// evaluates the generic PreToolUse contract. `vendor <name>` adapts supported
// vendor lifecycle events to the same S1-S5 assurance implementation.
package main

import (
	"encoding/json"
	"io"
	"os"

	"github.com/tomo-chan/agent-harness/internal/buildinfo"
	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/trustedexec"
	"github.com/tomo-chan/agent-harness/internal/vendor"
)

type preToolEvaluator struct{}
func (preToolEvaluator) Evaluate(a policy.Action) (policy.Decision,error) { return trustedexec.EvaluateAction(a) }
type completionEvaluator struct{}
func (completionEvaluator) Evaluate(r completion.Request) (completion.Result,error) { return trustedexec.EvaluateCompletion(r) }
type sessionProvider struct{}
func (sessionProvider) Context(cwd string) (string,error) { return trustedexec.SessionContext(cwd) }

func runVendor(name string) int {
	var v vendor.Name
	switch name { case string(vendor.Claude): v=vendor.Claude; case string(vendor.Codex):v=vendor.Codex; case string(vendor.Devin):v=vendor.Devin; default:v=vendor.Name(name) }
	raw, err := io.ReadAll(io.LimitReader(os.Stdin, (1<<20)+1))
	if err != nil || len(raw) > 1<<20 {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"decision":"block","reason":"invalid or oversized hook input"})
		return 2
	}
	response, handleErr := vendor.Handle(v, raw, vendor.Dependencies{PreTool:preToolEvaluator{},Completion:completionEvaluator{},Session:sessionProvider{}})
	if err := json.NewEncoder(os.Stdout).Encode(response); err != nil { return 2 }
	if handleErr != nil { return 2 }
	return 0
}

func main() {
	args:=os.Args[1:]
	if len(args)==1 && args[0]=="version" {
		if err:=json.NewEncoder(os.Stdout).Encode(buildinfo.Current()); err!=nil { os.Exit(2) }
		return
	}
	if len(args)==2 && args[0]=="vendor" { os.Exit(runVendor(args[1])) }
	os.Exit(trustedexec.Run(os.Stdin,os.Stdout,args))
}
