// Package controlplane reviews the concrete Git diff that an otherwise
// autonomous publication would expose. It runs after Publication Guard has
// established a fresh READY repository and an allow decision.
package controlplane

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

var protectedPrefixes = []string{
	".agent-harness/", ".claude/", ".codex/", ".devin/",
	".github/workflows/", "reference/claude/", "reference/codex/",
	"reference/harness/", "reference/hooks/", "reference/posture/",
	"reference/policies/", "reference/launcher/", "reference/scripts/",
	"reference/kubernetes/", "internal/",
}

var protectedFiles = map[string]struct{}{
	"AGENTS.md": {}, ".github/pull_request_template.md": {},
	"main.go": {}, "go.mod": {}, "go.sum": {},
}

// GitHub provides the authoritative default-branch head. The implementation
// must use the same fixed, trusted GitHub endpoint family as repository
// authority; local remote-tracking refs are not authority.
type GitHub interface {
	BranchHead(context.Context, string, string) (string, string, error)
}

// IsProtectedPath reports whether a repository-relative path belongs to the
// Agent Harness control plane.
func IsProtectedPath(path string) bool {
	path = strings.ReplaceAll(path, "\\", "/")
	for strings.HasPrefix(path, "./") {
		path = strings.TrimPrefix(path, "./")
	}
	if _, ok := protectedFiles[path]; ok {
		return true
	}
	for _, prefix := range protectedPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}

func withDecision(result policy.Decision, outcome, reason, rule string) policy.Decision {
	d := policy.Result(outcome, reason, rule)
	d.Evidence = result.Evidence
	return d
}

func addCheck(result *policy.Decision, name, status, detail string) error {
	if result.Evidence == nil || result.Evidence.Publication == nil {
		return fmt.Errorf("publication evidence is required for control-plane review")
	}
	result.Evidence.Publication.Checks = append(result.Evidence.Publication.Checks, policy.PublicationCheckEvidence{
		Name: name, Status: status, Detail: detail,
	})
	return nil
}

// Evaluate upgrades an otherwise autonomous publication to ask when its actual
// base...HEAD diff contains protected control-plane paths. Missing authority,
// missing local commit objects, or an unestablishable diff fail closed and
// return an error so the trusted runtime can preserve Evidence and exit 2.
func Evaluate(ctx context.Context, action policy.Action, result policy.Decision, report repository.Report, git repository.Git, github GitHub) (policy.Decision, error) {
	if result.Decision != "allow" {
		return result, nil
	}
	if report.State != "READY" || report.Repository == "" || report.DefaultBranch == "" || report.HeadSHA == "" {
		_ = addCheck(&result, "control_plane_authority", "fail", "fresh READY repository evidence is required")
		return withDecision(result, "deny", "repository authority does not permit control-plane publication review", "control-plane-authority"), nil
	}
	if git == nil || github == nil {
		_ = addCheck(&result, "control_plane_provider", "unknown", "Git and GitHub providers are required")
		return withDecision(result, "deny", "control-plane publication evidence is unavailable", "control-plane-evidence-error"), fmt.Errorf("control-plane provider unavailable")
	}

	baseSHA, digest, err := github.BranchHead(ctx, report.Repository, report.DefaultBranch)
	if err != nil || baseSHA == "" {
		_ = addCheck(&result, "default_branch_head", "unknown", "authoritative GitHub default-branch head is unavailable")
		if err == nil {
			err = fmt.Errorf("empty default-branch head")
		}
		return withDecision(result, "deny", "control-plane publication evidence is unavailable", "control-plane-evidence-error"), err
	}
	if err := addCheck(&result, "default_branch_head", "pass", baseSHA+" sha256="+digest); err != nil {
		return policy.Decision{}, err
	}

	if _, err := git.Run(ctx, action.CWD, "cat-file", "-e", baseSHA+"^{commit}"); err != nil {
		_ = addCheck(&result, "base_commit", "unknown", "authoritative GitHub base commit is not available locally")
		return withDecision(result, "deny", "control-plane publication base commit is unavailable", "control-plane-evidence-error"), err
	}
	_ = addCheck(&result, "base_commit", "pass", baseSHA)

	// Disable rename detection so both the deleted source and added destination
	// are returned. NUL termination preserves non-ASCII, newline, and other path
	// bytes without core.quotePath display escaping.
	changed, err := git.Run(ctx, action.CWD, "diff", "--no-renames", "--name-only", "-z", baseSHA+"..."+report.HeadSHA)
	if err != nil {
		_ = addCheck(&result, "publication_diff", "unknown", "cannot establish diff against authoritative GitHub default branch")
		return withDecision(result, "deny", "control-plane publication diff is unavailable", "control-plane-evidence-error"), err
	}
	var protected []string
	for _, path := range strings.Split(changed, "\x00") {
		if path != "" && IsProtectedPath(path) {
			protected = append(protected, path)
		}
	}
	sort.Strings(protected)
	if len(protected) == 0 {
		_ = addCheck(&result, "control_plane_paths", "pass", "publication diff contains no protected control-plane path")
		return result, nil
	}

	detail := strings.Join(protected, ", ")
	if len(protected) > 5 {
		detail = strings.Join(protected[:5], ", ") + fmt.Sprintf(" (+%d more)", len(protected)-5)
	}
	_ = addCheck(&result, "control_plane_paths", "fail", detail)
	return withDecision(result, "ask", "publishing control-plane changes requires explicit review: "+detail, "control-plane-publication"), nil
}
