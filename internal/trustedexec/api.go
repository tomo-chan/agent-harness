package trustedexec

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/tomo-chan/agent-harness/internal/completion"
	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

// EvaluateAction lets a trusted vendor adapter invoke the same S1-S4 runtime
// used by the generic hook without selecting an alternate evaluator.
func EvaluateAction(action policy.Action) (policy.Decision, error) {
	payload, err := json.Marshal(map[string]any{"tool": action.Tool, "input": action.Input, "cwd": action.CWD})
	if err != nil { return policy.Decision{}, err }
	rt := runtime{
		executable: os.Executable, getenv: os.Getenv,
		authority: productionAuthority, publication: productionPublication, controlPlane: productionControlPlane,
	}
	d, failure := rt.evaluate(bytes.NewReader(payload), nil)
	if failure != "" { return d, fmt.Errorf("%s", failure) }
	return d, nil
}

// CompletionGatePath binds completion to one fixed trusted executable next to
// the Agent Harness binary. Repository content cannot replace the gate.
func CompletionGatePath(executable, configured string) (string, error) {
	p, err := trustedFilePath(executable, configured, "completion-gate")
	if err != nil { return "", err }
	info, err := os.Stat(p); if err != nil { return "", err }
	if info.Mode().Perm()&0o111 == 0 { return "", fmt.Errorf("completion gate must be executable") }
	return p, nil
}

type trustedCompletionGate struct { path string }
func (g trustedCompletionGate) Check(ctx context.Context, cwd string) (string, error) {
	command := exec.CommandContext(ctx, g.path)
	command.Dir = cwd
	command.Env = []string{"HOME=/nonexistent", "LC_ALL=C", "PATH=/usr/bin:/bin"}
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout; command.Stderr = &stderr
	err := command.Run()
	detail := strings.TrimSpace(stdout.String()+"\n"+stderr.String())
	if len(detail) > 16<<10 { detail = detail[:16<<10] }
	if err != nil {
		if ctx.Err() != nil { return detail, fmt.Errorf("completion gate timed out or was cancelled") }
		return detail, fmt.Errorf("completion gate failed")
	}
	if detail == "" { detail = "trusted completion gate passed" }
	return detail, nil
}

// EvaluateCompletion performs a fresh Stop-time repository assessment and then
// applies S5. The repository policy and gate are fixed relative to the trusted
// binary; SessionStart state is not consulted.
func EvaluateCompletion(req completion.Request) (completion.Result, error) {
	for _, name := range unsupportedSelectors {
		if os.Getenv(name) != "" {
			return completion.Result{Outcome: completion.OutcomeBlocked, Reason: "unsupported trusted-runtime override"}, fmt.Errorf("unsupported override")
		}
	}
	exe, err := os.Executable(); if err != nil { return completion.Result{Outcome: completion.OutcomeBlocked, Reason:"trusted executable unavailable"}, err }
	root := os.Getenv("AGENT_HARNESS_TRUSTED_ROOT")
	repositoryPath, err := RepositoryPolicyPath(exe, root); if err != nil { return completion.Result{Outcome: completion.OutcomeBlocked, Reason:"trusted repository policy unavailable"}, err }
	gatePath, err := CompletionGatePath(exe, root); if err != nil { return completion.Result{Outcome: completion.OutcomeBlocked, Reason:"trusted completion gate unavailable"}, err }
	f, err := os.Open(repositoryPath); if err != nil { return completion.Result{Outcome: completion.OutcomeBlocked, Reason:"trusted repository policy unavailable"}, err }; defer f.Close()
	config, err := repository.LoadConfig(f); if err != nil { return completion.Result{Outcome: completion.OutcomeBlocked, Reason:"invalid trusted repository policy"}, err }
	ctx, cancel := context.WithTimeout(context.Background(), 135*time.Second); defer cancel()
	git := repository.SystemGit{Path:"/usr/bin/git"}
	github := repository.NewGitHubClient(os.Getenv("AGENT_HARNESS_GITHUB_TOKEN"))
	report, authorityErr := repository.AssessCompletion(ctx, req.CWD, config, git, github, time.Now())
	if authorityErr != nil {
		return completion.Result{Outcome: completion.OutcomeBlocked, Reason: report.Summary(), Evidence: completion.Evidence{Repository:report.Repository,Branch:report.Branch,LocalHeadSHA:report.HeadSHA,DefaultBranch:report.DefaultBranch}}, authorityErr
	}
	return completion.Evaluate(ctx, req, report, git, github, trustedCompletionGate{path:gatePath}), nil
}

// SessionContext intentionally returns no authoritative snapshot. It reminds
// the agent that fresh assurance is performed at mutation/publication/Stop time.
func SessionContext(string) (string, error) {
	return "Agent Harness will re-evaluate repository authority and completion evidence at action/Stop time; SessionStart context is not authority.", nil
}
