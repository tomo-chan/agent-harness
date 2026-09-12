// Package trustedexec binds the generic adapter and trusted configuration to
// this executable. Deployment MUST keep the installation and its ancestors
// immutable to the repository/agent and invoke the genuine binary with trusted
// environment. Path checks cannot prove ownership, mount immutability, or
// prevent replacement races by an actor who can write the installation.
package trustedexec

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

func trustedFilePath(executable, configured, name string) (string, error) {
	if !filepath.IsAbs(configured) {
		return "", fmt.Errorf("absolute trusted root required")
	}
	root, err := filepath.EvalSymlinks(configured)
	if err != nil {
		return "", err
	}
	exe, err := filepath.EvalSymlinks(executable)
	if err != nil {
		return "", err
	}
	if filepath.Dir(exe) != root {
		return "", fmt.Errorf("trusted root mismatch")
	}
	rootInfo, err := os.Stat(root)
	if err != nil || !rootInfo.IsDir() {
		return "", fmt.Errorf("trusted root must be a directory")
	}
	p, err := filepath.EvalSymlinks(filepath.Join(root, name))
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(root, p)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", fmt.Errorf("policy outside trusted root")
	}
	info, err := os.Stat(p)
	if err != nil {
		return "", err
	}
	if !info.Mode().IsRegular() {
		return "", fmt.Errorf("policy must be a regular file")
	}
	return p, nil
}

// PolicyPath requires an absolute root matching the canonical executable parent.
// policy.json is the only tool-policy location; there is no repository fallback.
func PolicyPath(executable, configured string) (string, error) {
	return trustedFilePath(executable, configured, "policy.json")
}

// RepositoryPolicyPath binds Repository Authority / Posture to the fixed
// repository-security.json file in the same trusted root as the executable.
func RepositoryPolicyPath(executable, configured string) (string, error) {
	return trustedFilePath(executable, configured, repository.ConfigFilename)
}

var unsupportedSelectors = []string{
	"AGENT_HARNESS_TRUSTED_ADAPTER",
	"AGENT_HARNESS_TRUSTED_POLICY",
	"AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY",
	"AGENT_HARNESS_REPOSITORY_SECURITY_POLICY",
	"AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY",
	"AGENT_HARNESS_EXPECTED_REPOSITORY",
	"AGENT_HARNESS_MINIMUM_POSTURE_MODE",
	"AGENT_HARNESS_STATE_DIR",
	"SSL_CERT_FILE",
	"SSL_CERT_DIR",
}

type authorityEvaluator func(context.Context, policy.Action, *repository.Config) (repository.Report, error)

type runtime struct {
	executable func() (string, error)
	getenv     func(string) string
	authority  authorityEvaluator
}

func productionAuthority(ctx context.Context, action policy.Action, config *repository.Config) (repository.Report, error) {
	return repository.Assess(
		ctx,
		action,
		config,
		repository.SystemGit{Path: "/usr/bin/git"},
		repository.NewGitHubClient(os.Getenv("AGENT_HARNESS_GITHUB_TOKEN")),
		time.Now(),
	)
}

func (rt runtime) evaluate(in io.Reader, args []string) (policy.Decision, string) {
	if len(args) != 0 {
		return policy.Decision{}, "unexpected-arguments"
	}
	// Repository or legacy launcher selectors cannot replace trusted files,
	// identity, posture requirements, or cache state in the Go implementation.
	for _, name := range unsupportedSelectors {
		if rt.getenv(name) != "" {
			return policy.Decision{}, "unsupported-override"
		}
	}
	exe, err := rt.executable()
	if err != nil {
		return policy.Decision{}, "trusted-path-error"
	}
	root := rt.getenv("AGENT_HARNESS_TRUSTED_ROOT")
	p, err := PolicyPath(exe, root)
	if err != nil {
		return policy.Decision{}, "trusted-path-error"
	}
	repositoryPolicyPath, err := RepositoryPolicyPath(exe, root)
	if err != nil {
		return policy.Decision{}, "trusted-path-error"
	}
	f, err := os.Open(p)
	if err != nil {
		return policy.Decision{}, "policy-error"
	}
	defer f.Close()
	e, err := policy.Load(f)
	if err != nil {
		return policy.Decision{}, "policy-error"
	}
	repositoryFile, err := os.Open(repositoryPolicyPath)
	if err != nil {
		return policy.Decision{}, "repository-policy-error"
	}
	defer repositoryFile.Close()
	repositoryConfig, err := repository.LoadConfig(repositoryFile)
	if err != nil {
		return policy.Decision{}, "repository-policy-error"
	}
	a, err := policy.ParseHook(in)
	if err != nil {
		return policy.Decision{}, "input-error"
	}
	d, err := e.Evaluate(a)
	if err != nil {
		return policy.Decision{}, "evaluation-error"
	}
	if d.Decision == "deny" || !repository.RequiresAuthority(a) {
		return d, ""
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	report, err := rt.authority(ctx, a, repositoryConfig)
	if d.Evidence == nil {
		return policy.Decision{}, "repository-authority-error"
	}
	checks := make([]policy.RepositoryCheckEvidence, len(report.Checks))
	for i, check := range report.Checks {
		checks[i] = policy.RepositoryCheckEvidence{Name: check.Name, Status: check.Status, Detail: check.Detail}
	}
	d.Evidence.Repository = &policy.RepositoryEvidence{
		PolicySHA256:           report.Evidence.RepositoryPolicySHA256,
		PostureState:           report.State,
		Repository:             report.Repository,
		RepositoryID:           report.RepositoryID,
		RepoRoot:               report.RepoRoot,
		MutationTarget:         report.MutationTarget,
		Branch:                 report.Branch,
		HeadSHA:                report.HeadSHA,
		DefaultBranch:          report.DefaultBranch,
		LinkedWorktree:         report.LinkedWorktree,
		AuthoritySource:        report.Evidence.AuthoritySource,
		MetadataSHA256:         report.Evidence.GitHubMetadataSHA256,
		DefaultAuthoritySHA256: report.Evidence.GitHubDefaultAuthoritySHA256,
		CurrentAuthoritySHA256: report.Evidence.GitHubCurrentAuthoritySHA256,
		CheckedAt:              report.Evidence.CheckedAt,
		Checks:                 checks,
	}
	if err != nil {
		failed := policy.Result("deny", "Agent Harness evaluation failed: repository-authority-error", "repository-authority-error")
		failed.Evidence = d.Evidence
		return failed, "repository-authority-error"
	}
	if report.State != "READY" {
		denied := policy.Result("deny", report.Summary(), "repository-authority")
		denied.Evidence = d.Evidence
		return denied, ""
	}
	return d, ""
}

func (rt runtime) run(in io.Reader, out io.Writer, args []string) int {
	d, failure := rt.evaluate(in, args)
	code := 0
	if failure != "" {
		if d.Decision == "" {
			d = policy.Result("deny", "Agent Harness evaluation failed: "+failure, failure)
		}
		code = 2
	}
	if err := json.NewEncoder(out).Encode(d); err != nil {
		return 2
	}
	return code
}

// Run emits one decision. A valid allow/ask/deny exits 0; configuration, input,
// or authoritative-state errors emit deny and exit 2. Output failure exits 2.
// The caller must deny on nonzero exit, missing/malformed output, crash, or
// timeout; ask is not permission.
func Run(in io.Reader, out io.Writer, args []string) int {
	rt := runtime{executable: os.Executable, getenv: os.Getenv, authority: productionAuthority}
	return rt.run(in, out, args)
}
