package repository

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type fakeGit map[string]string

func (f fakeGit) Run(_ context.Context, _ string, args ...string) (string, error) {
	key := strings.Join(args, " ")
	value, ok := f[key]
	if !ok {
		return "", errors.New("unexpected git query: " + key)
	}
	if strings.HasPrefix(value, "error:") {
		return "", errors.New(strings.TrimPrefix(value, "error:"))
	}
	return value, nil
}

type fakeGitHub struct {
	metadata Metadata
	rules    map[string]bool
	metaErr  error
	rulesErr error
}

func (f fakeGitHub) Repository(context.Context, string) (Metadata, string, error) {
	return f.metadata, "metadata-digest", f.metaErr
}

func (f fakeGitHub) EffectiveRuleTypes(context.Context, string, string) (map[string]bool, string, error) {
	return f.rules, "rules-digest", f.rulesErr
}

func readyInputs(t *testing.T) (string, *Config, fakeGit, fakeGitHub) {
	t.Helper()
	root := t.TempDir()
	gitDir := filepath.Join(t.TempDir(), "common", "worktrees", "task")
	commonDir := filepath.Join(filepath.Dir(filepath.Dir(gitDir)), ".git")
	for _, directory := range []string{gitDir, commonDir} {
		if err := os.MkdirAll(directory, 0o700); err != nil {
			t.Fatal(err)
		}
	}
	config := &Config{
		SchemaVersion:      1,
		ExpectedRepository: "acme/widget",
		SHA256:             "policy-digest",
		Requirements: Requirements{
			RequireLinkedWorktree: true,
			RequirePullRequest:    true,
			BlockForcePush:        true,
			RequiredStatusChecks:  true,
		},
	}
	git := fakeGit{
		"rev-parse --show-toplevel":                            root,
		"config --local --no-includes --get remote.origin.url": "https://github.com/acme/widget.git",
		"rev-parse --abbrev-ref HEAD":                          "feature/task",
		"rev-parse HEAD":                                       strings.Repeat("a", 40),
		"rev-parse --absolute-git-dir":                         gitDir,
		"rev-parse --path-format=absolute --git-common-dir":    commonDir,
	}
	github := fakeGitHub{
		metadata: Metadata{FullName: "acme/widget", DefaultBranch: "main"},
		rules: map[string]bool{
			"pull_request":           true,
			"non_fast_forward":       true,
			"required_status_checks": true,
		},
	}
	return root, config, git, github
}

func TestAssessRejectsUnvalidatedConfiguration(t *testing.T) {
	report, err := Assess(context.Background(), "/work", nil, nil, nil, time.Now())
	if err == nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "repository_policy=unknown") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessReadyUsesFreshLocalAndGitHubEvidence(t *testing.T) {
	root, config, git, github := readyInputs(t)
	report, err := Assess(context.Background(), root, config, git, github, time.Unix(1_000, 0))
	if err != nil {
		t.Fatal(err)
	}
	if report.State != "READY" || report.Branch != "feature/task" || !report.LinkedWorktree {
		t.Fatalf("unexpected report: %+v", report)
	}
	if report.Evidence.RepositoryPolicySHA256 != "policy-digest" ||
		report.Evidence.GitHubMetadataSHA256 != "metadata-digest" ||
		report.Evidence.GitHubRulesSHA256 != "rules-digest" {
		t.Fatalf("missing evidence: %+v", report.Evidence)
	}
}

func TestSystemGitUsesFixedExecutableWithSanitizedSelectors(t *testing.T) {
	if _, err := os.Stat("/usr/bin/git"); err != nil {
		t.Skip("production Git path is unavailable on this platform")
	}
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("GIT_DIR", t.TempDir())
	root, err := (SystemGit{Path: "/usr/bin/git"}).Run(context.Background(), cwd, "rev-parse", "--show-toplevel")
	if err != nil || root == "" {
		t.Fatalf("root=%q err=%v", root, err)
	}
}

func TestBoundedGitOutputDoesNotAccumulateRepositoryControlledData(t *testing.T) {
	buffer := boundedBuffer{limit: 4}
	written, err := buffer.Write([]byte("untrusted-output"))
	if err != nil || written != len("untrusted-output") || !buffer.exceeded || buffer.buffer.Len() != 4 {
		t.Fatalf("written=%d err=%v exceeded=%t length=%d", written, err, buffer.exceeded, buffer.buffer.Len())
	}
}

func TestAssessBlocksTrustedIdentityMismatchBeforeGitHub(t *testing.T) {
	root, config, git, github := readyInputs(t)
	git["config --local --no-includes --get remote.origin.url"] = "https://github.com/acme/other.git"
	report, err := Assess(context.Background(), root, config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "repository_identity=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessBlocksDefaultBranchAndControlCheckout(t *testing.T) {
	root, config, git, github := readyInputs(t)
	git["rev-parse --abbrev-ref HEAD"] = "main"
	git["rev-parse --absolute-git-dir"] = git["rev-parse --path-format=absolute --git-common-dir"]
	report, err := Assess(context.Background(), root, config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	if !strings.Contains(report.Summary(), "linked_worktree=fail") || !strings.Contains(report.Summary(), "default_branch=fail") {
		t.Fatalf("missing branch/worktree denial: %s", report.Summary())
	}
}

func TestAssessBlocksMissingRequiredRule(t *testing.T) {
	root, config, git, github := readyInputs(t)
	delete(github.rules, "required_status_checks")
	report, err := Assess(context.Background(), root, config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "required_status_checks=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessPreservesUnknownAndFailsClosedOnGitHubError(t *testing.T) {
	root, config, git, github := readyInputs(t)
	github.rulesErr = errors.New("HTTP 403")
	report, err := Assess(context.Background(), root, config, git, github, time.Now())
	if err == nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "github_rules=unknown") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestParseGitHubRepository(t *testing.T) {
	for raw, want := range map[string]string{
		"https://github.com/acme/widget.git":   "acme/widget",
		"git@github.com:acme/widget.git":       "acme/widget",
		"ssh://git@github.com/acme/widget.git": "acme/widget",
	} {
		if got, ok := ParseGitHubRepository(raw); !ok || got != want {
			t.Errorf("%q => %q, %t", raw, got, ok)
		}
	}
	for _, raw := range []string{
		"https://example.com/acme/widget",
		"file:///tmp/widget",
		"https://github.com/acme/widget/extra",
		"https://github.com:8443/acme/widget",
		"https://user@github.com/acme/widget",
		"ssh://other@github.com/acme/widget",
		"https://github.com/acme/widget?redirect=true",
	} {
		if _, ok := ParseGitHubRepository(raw); ok {
			t.Errorf("accepted %q", raw)
		}
	}
}
