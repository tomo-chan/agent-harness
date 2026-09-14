package completion

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/tomo-chan/agent-harness/internal/repository"
)

type fakeGit struct { values map[string]string; failures map[string]error }
func (g fakeGit) Run(_ context.Context, _ string, args ...string) (string,error) { k:=strings.Join(args," "); if err:=g.failures[k];err!=nil{return "",err}; return g.values[k],nil }

type fakeGitHub struct { head string; err error }
func (g fakeGitHub) BranchHead(context.Context,string,string)(string,string,error){ return g.head,"digest",g.err }

type fakeGate struct { called *bool; detail string; err error }
func (g fakeGate) Check(context.Context,string)(string,error){ if g.called!=nil{*g.called=true}; return g.detail,g.err }

func report(branch string) repository.Report { return repository.Report{State:"READY",Repository:"acme/widget",Branch:branch,HeadSHA:strings.Repeat("a",40),DefaultBranch:"main"} }

func TestCleanDefaultBranchRequiresAgentReviewFirst(t *testing.T){
	head:=strings.Repeat("a",40); gateCalled:=false
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"main","rev-parse HEAD":head,"status --porcelain=v1 --untracked-files=all":""}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("main"),g,fakeGitHub{head:head},fakeGate{called:&gateCalled,detail:"should not run"})
	if r.Outcome!=OutcomeReviewRequired||gateCalled||!r.Evidence.NoDeliveryDelta{t.Fatalf("%+v gate=%t",r,gateCalled)}
}

func TestFollowUpCanCompleteAfterDeterministicRecheck(t *testing.T){
	head:=strings.Repeat("a",40)
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"main","rev-parse HEAD":head,"status --porcelain=v1 --untracked-files=all":""}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo",FollowUp:true},report("main"),g,fakeGitHub{head:head},fakeGate{})
	if r.Outcome!=OutcomeComplete{t.Fatalf("%+v",r)}
}

func TestFeatureBranchUsesDeterministicGate(t *testing.T){
	head:=strings.Repeat("a",40); called:=false
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"feature/task","rev-parse HEAD":head}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("feature/task"),g,fakeGitHub{},fakeGate{called:&called,detail:"tests and delivery checks passed"})
	if r.Outcome!=OutcomeReviewRequired||!called||r.Evidence.NoDeliveryDelta{t.Fatalf("%+v called=%t",r,called)}
}

func TestGateFailureBlocksCompletion(t *testing.T){
	head:=strings.Repeat("a",40)
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"feature/task","rev-parse HEAD":head}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("feature/task"),g,fakeGitHub{},fakeGate{detail:"CI failed",err:errors.New("exit 1")})
	if r.Outcome!=OutcomeBlocked{t.Fatalf("%+v",r)}
}

func TestDirtyDefaultBranchDoesNotUseNoDeltaShortcut(t *testing.T){
	head:=strings.Repeat("a",40); called:=false
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"main","rev-parse HEAD":head,"status --porcelain=v1 --untracked-files=all":"?? new.txt"}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("main"),g,fakeGitHub{head:head},fakeGate{called:&called,detail:"gate passed"})
	if r.Outcome!=OutcomeReviewRequired||!called||r.Evidence.NoDeliveryDelta{t.Fatalf("%+v called=%t",r,called)}
}

func TestGitHubMismatchDoesNotUseNoDeltaShortcut(t *testing.T){
	head:=strings.Repeat("a",40); called:=false
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"main","rev-parse HEAD":head,"status --porcelain=v1 --untracked-files=all":""}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("main"),g,fakeGitHub{head:strings.Repeat("b",40)},fakeGate{called:&called,detail:"gate passed"})
	if r.Outcome!=OutcomeReviewRequired||!called||r.Evidence.NoDeliveryDelta{t.Fatalf("%+v called=%t",r,called)}
}

func TestFreshAuthorityAndHeadAreRechecked(t *testing.T){
	head:=strings.Repeat("a",40)
	g:=fakeGit{values:map[string]string{"rev-parse --abbrev-ref HEAD":"feature/other","rev-parse HEAD":head}}
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("feature/task"),g,fakeGitHub{},fakeGate{})
	if r.Outcome!=OutcomeBlocked{t.Fatalf("%+v",r)}
}

func TestMissingProviderFailsClosed(t *testing.T){
	r:=Evaluate(context.Background(),Request{CWD:"/repo"},report("feature/task"),nil,nil,nil)
	if r.Outcome!=OutcomeBlocked{t.Fatalf("%+v",r)}
}
