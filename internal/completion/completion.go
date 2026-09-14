// Package completion implements vendor-independent deterministic completion assurance.
// It produces evidence for the agent's semantic completion review; deterministic
// success alone is never interpreted as semantic task completion.
package completion

import (
	"context"
	"fmt"
	"strings"

	"github.com/tomo-chan/agent-harness/internal/repository"
)

type Outcome string

const (
	OutcomeBlocked        Outcome = "blocked"
	OutcomeReviewRequired Outcome = "review_required"
	OutcomeComplete       Outcome = "complete"
)

type Check struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}

type Evidence struct {
	Repository       string  `json:"repository"`
	Branch           string  `json:"branch"`
	LocalHeadSHA     string  `json:"local_head_sha"`
	DefaultBranch    string  `json:"default_branch"`
	GitHubDefaultSHA string  `json:"github_default_sha,omitempty"`
	NoDeliveryDelta  bool    `json:"no_delivery_delta"`
	Checks           []Check `json:"checks"`
}

type Result struct {
	Outcome  Outcome  `json:"outcome"`
	Reason   string   `json:"reason"`
	Evidence Evidence `json:"evidence"`
}

type Request struct {
	CWD      string
	FollowUp bool
}

type GitHub interface {
	BranchHead(context.Context, string, string) (string, string, error)
}

// Gate executes repository-specific deterministic delivery checks when the
// no-delivery-delta shortcut cannot be proven.
type Gate interface {
	Check(context.Context, string) (string, error)
}

func add(e *Evidence, name, status, detail string) {
	e.Checks = append(e.Checks, Check{Name: name, Status: status, Detail: detail})
}

func blocked(e Evidence, reason string) Result {
	return Result{Outcome: OutcomeBlocked, Reason: reason, Evidence: e}
}

// Evaluate consumes a fresh Repository Authority report produced at Stop time.
// It does not accept SessionStart snapshots or local remote-tracking refs as authority.
func Evaluate(ctx context.Context, req Request, report repository.Report, git repository.Git, github GitHub, gate Gate) Result {
	e := Evidence{Repository: report.Repository, Branch: report.Branch, LocalHeadSHA: report.HeadSHA, DefaultBranch: report.DefaultBranch}
	if req.CWD == "" || report.State != "READY" || report.Repository == "" || report.Branch == "" || report.HeadSHA == "" || report.DefaultBranch == "" {
		add(&e, "repository_authority", "fail", "fresh READY repository evidence is required at Stop")
		return blocked(e, "deterministic completion assurance cannot establish repository authority")
	}
	add(&e, "repository_authority", "pass", "fresh READY repository evidence supplied")
	if git == nil || github == nil || gate == nil {
		add(&e, "completion_provider", "unknown", "Git, GitHub, and deterministic gate providers are required")
		return blocked(e, "deterministic completion evidence is unavailable")
	}

	branch, err := git.Run(ctx, req.CWD, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil || branch == "" || branch == "HEAD" {
		add(&e, "current_branch", "unknown", "current branch is unavailable")
		return blocked(e, "deterministic completion evidence is unavailable")
	}
	if branch != report.Branch {
		add(&e, "current_branch", "fail", "branch changed after fresh repository authority evaluation")
		return blocked(e, "current branch no longer matches repository authority")
	}
	add(&e, "current_branch", "pass", branch)

	head, err := git.Run(ctx, req.CWD, "rev-parse", "HEAD")
	if err != nil || head == "" {
		add(&e, "local_head", "unknown", "local HEAD is unavailable")
		return blocked(e, "deterministic completion evidence is unavailable")
	}
	if head != report.HeadSHA {
		add(&e, "local_head", "fail", "HEAD changed after fresh repository authority evaluation")
		return blocked(e, "local HEAD no longer matches repository authority")
	}
	add(&e, "local_head", "pass", head)

	noDelta := false
	if branch == report.DefaultBranch {
		status, statusErr := git.Run(ctx, req.CWD, "status", "--porcelain=v1", "--untracked-files=all")
		if statusErr != nil {
			add(&e, "clean_worktree", "unknown", "worktree status is unavailable")
		} else if status != "" {
			add(&e, "clean_worktree", "fail", "worktree contains tracked or untracked changes")
		} else {
			add(&e, "clean_worktree", "pass", "worktree is clean including untracked files")
			remoteHead, _, remoteErr := github.BranchHead(ctx, report.Repository, report.DefaultBranch)
			if remoteErr != nil || remoteHead == "" {
				add(&e, "github_default_head", "unknown", "GitHub default-branch head is unavailable")
			} else {
				e.GitHubDefaultSHA = remoteHead
				if remoteHead == head {
					add(&e, "github_default_head", "pass", remoteHead)
					noDelta = true
				} else {
					add(&e, "github_default_head", "fail", "local default branch differs from GitHub authority")
				}
			}
		}
	}

	if noDelta {
		e.NoDeliveryDelta = true
		add(&e, "deterministic_gate", "pass", "no delivery delta; clean READY default branch matches GitHub head")
	} else {
		detail, gateErr := gate.Check(ctx, req.CWD)
		if gateErr != nil {
			if strings.TrimSpace(detail) == "" { detail = gateErr.Error() }
			add(&e, "deterministic_gate", "fail", detail)
			return blocked(e, "deterministic completion gate failed")
		}
		add(&e, "deterministic_gate", "pass", detail)
	}

	if !req.FollowUp {
		return Result{
			Outcome: OutcomeReviewRequired,
			Reason: "deterministic completion assurance passed; evaluate task requirements, execution results, unresolved concerns, and new findings before completing",
			Evidence: e,
		}
	}
	return Result{Outcome: OutcomeComplete, Reason: "deterministic completion assurance passed after agent completion review", Evidence: e}
}

// StaticGate is useful for adapters/tests that already executed a deterministic
// gate and need to supply its result without changing S5 semantics.
type StaticGate struct { Detail string; Err error }
func (g StaticGate) Check(context.Context, string) (string, error) {
	if g.Err != nil { return g.Detail, g.Err }
	if strings.TrimSpace(g.Detail) == "" { return "deterministic gate passed", nil }
	return g.Detail, nil
}

var _ = fmt.Sprintf
