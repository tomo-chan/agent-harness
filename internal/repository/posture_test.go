package repository

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/tomo-chan/agent-harness/internal/policy"
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
	metadata   Metadata
	branches   map[string]BranchMetadata
	rules      map[string]map[string]bool
	metaErr    error
	branchErr  map[string]error
	rulesError map[string]error
}

func (f fakeGitHub) Repository(context.Context, string) (Metadata, string, error) {
	return f.metadata, "metadata-digest", f.metaErr
}

func (f fakeGitHub) Branch(_ context.Context, _, branch string) (BranchMetadata, string, error) {
	return f.branches[branch], "branch-digest-" + branch, f.branchErr[branch]
}

func (f fakeGitHub) EffectiveRuleTypes(_ context.Context, _, branch string) (map[string]bool, string, error) {
	return f.rules[branch], "rules-digest-" + branch, f.rulesError[branch]
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
		SchemaVersion:        1,
		AuthoritySource:      AuthoritySourceGitHubRules,
		ExpectedRepository:   "acme/widget",
		ExpectedRepositoryID: 123456,
		ExpectedWorktreeRoot: root,
		ExpectedGitDir:       gitDir,
		ExpectedGitCommonDir: commonDir,
		ExpectedBranch:       "feature/task",
		SHA256:               "policy-digest",
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
		metadata: Metadata{ID: 123456, FullName: "acme/widget", DefaultBranch: "main"},
		branches: map[string]BranchMetadata{
			"feature/task": {Name: "feature/task", Protected: false},
			"main":         {Name: "main", Protected: true},
		},
		rules: map[string]map[string]bool{
			"feature/task": {},
			"main": {
				"pull_request":           true,
				"non_fast_forward":       true,
				"required_status_checks": true,
			},
		},
		branchErr:  map[string]error{},
		rulesError: map[string]error{},
	}
	return root, config, git, github
}

func mutationAction(root string) policy.Action {
	return policy.Action{Tool: "Write", CWD: root, Target: filepath.Join(root, "README.md")}
}

func TestAssessRejectsUnvalidatedConfiguration(t *testing.T) {
	report, err := Assess(context.Background(), policy.Action{Tool: "Write", CWD: "/work", Target: "/work/file"}, nil, nil, nil, time.Now())
	if err == nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "repository_policy=unknown") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessReadyUsesFreshLocalAndGitHubEvidence(t *testing.T) {
	root, config, git, github := readyInputs(t)
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Unix(1_000, 0))
	if err != nil {
		t.Fatal(err)
	}
	if report.State != "READY" || report.Branch != "feature/task" || !report.LinkedWorktree {
		t.Fatalf("unexpected report: %+v", report)
	}
	if report.Evidence.RepositoryPolicySHA256 != "policy-digest" ||
		report.Evidence.GitHubMetadataSHA256 != "metadata-digest" ||
		report.Evidence.AuthoritySource != AuthoritySourceGitHubRules ||
		report.Evidence.GitHubDefaultAuthoritySHA256 != "rules-digest-main" ||
		report.Evidence.GitHubCurrentAuthoritySHA256 != "rules-digest-feature/task" {
		t.Fatalf("missing evidence: %+v", report.Evidence)
	}
}

func TestAssessPublicationReusesRepositoryAuthorityWithoutDirectFileTarget(t *testing.T) {
	root, config, git, github := readyInputs(t)
	action := policy.Action{
		Tool: "exec", CWD: root,
		Input: map[string]any{"command": "git push origin HEAD:refs/heads/feature/task"},
	}
	report, err := AssessPublication(context.Background(), action, config, git, github, time.Unix(1_000, 0))
	if err != nil || report.State != "READY" || report.MutationTarget != "" {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	foundHandoff := false
	for _, check := range report.Checks {
		if check.Name == "publication_handoff" && check.Status == "pass" {
			foundHandoff = true
		}
	}
	if !foundHandoff {
		t.Fatalf("publication handoff evidence missing: %+v", report.Checks)
	}
}

func TestAssessCompletionAllowsReadOnlyDefaultBranchObservation(t *testing.T) {
	root, config, git, github := readyInputs(t)
	config.ExpectedBranch = "main"
	git["rev-parse --abbrev-ref HEAD"] = "main"
	report, err := AssessCompletion(context.Background(), policy.Action{Tool: "Stop", CWD: root}, config, git, github, time.Unix(1_000, 0))
	if err != nil || report.State != "READY" || report.Branch != "main" || report.MutationTarget != "" {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	foundHandoff := false
	for _, check := range report.Checks {
		if check.Name == "completion_handoff" && check.Status == "pass" {
			foundHandoff = true
		}
	}
	if !foundHandoff {
		t.Fatalf("completion handoff evidence missing: %+v", report.Checks)
	}
}

func TestAssessReadyWithAvailableGitHubBranchMetadataSource(t *testing.T) {
	root, config, git, github := readyInputs(t)
	config.AuthoritySource = AuthoritySourceGitHubBranchMetadata
	config.Requirements.RequirePullRequest = false
	config.Requirements.BlockForcePush = false
	config.Requirements.RequiredStatusChecks = false
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Unix(1_000, 0))
	if err != nil || report.State != "READY" {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	if report.Evidence.AuthoritySource != AuthoritySourceGitHubBranchMetadata ||
		report.Evidence.GitHubCurrentAuthoritySHA256 != "branch-digest-feature/task" ||
		report.Evidence.GitHubDefaultAuthoritySHA256 != "" {
		t.Fatalf("unexpected source evidence: %+v", report.Evidence)
	}
}

func TestAssessBranchMetadataSourceFailsClosed(t *testing.T) {
	for _, mutate := range []func(*Config, *fakeGitHub){
		func(_ *Config, github *fakeGitHub) {
			github.branches["feature/task"] = BranchMetadata{Name: "feature/task", Protected: true}
		},
		func(_ *Config, github *fakeGitHub) { github.branchErr["feature/task"] = errors.New("HTTP 403") },
		func(config *Config, _ *fakeGitHub) { config.Requirements.RequirePullRequest = true },
	} {
		root, config, git, github := readyInputs(t)
		config.AuthoritySource = AuthoritySourceGitHubBranchMetadata
		config.Requirements.RequirePullRequest = false
		config.Requirements.BlockForcePush = false
		config.Requirements.RequiredStatusChecks = false
		mutate(config, &github)
		report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
		if report.State != "BLOCKED" {
			t.Fatalf("report=%+v err=%v", report, err)
		}
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

func TestAssessBindsAnActualLinkedWorktree(t *testing.T) {
	const gitPath = "/usr/bin/git"
	if _, err := os.Stat(gitPath); err != nil {
		t.Skip("production Git path is unavailable on this platform")
	}
	base := t.TempDir()
	control := filepath.Join(base, "control")
	worktree := filepath.Join(base, "task")
	runTestGit(t, gitPath, "init", control)
	if err := os.WriteFile(filepath.Join(control, "README.md"), []byte("test\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	runTestGit(t, gitPath, "-C", control, "add", "README.md")
	runTestGit(t, gitPath, "-C", control, "-c", "user.name=Agent Harness Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial")
	runTestGit(t, gitPath, "-C", control, "branch", "-M", "main")
	runTestGit(t, gitPath, "-C", control, "remote", "add", "origin", "https://github.com/acme/widget.git")
	runTestGit(t, gitPath, "-C", control, "worktree", "add", "-b", "feature/task", worktree)

	git := SystemGit{Path: gitPath}
	gitDir, err := git.Run(context.Background(), worktree, "rev-parse", "--absolute-git-dir")
	if err != nil {
		t.Fatal(err)
	}
	commonDir, err := git.Run(context.Background(), worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if err != nil {
		t.Fatal(err)
	}
	config := &Config{
		SchemaVersion:        1,
		AuthoritySource:      AuthoritySourceGitHubRules,
		ExpectedRepository:   "acme/widget",
		ExpectedRepositoryID: 123456,
		ExpectedWorktreeRoot: worktree,
		ExpectedGitDir:       gitDir,
		ExpectedGitCommonDir: commonDir,
		ExpectedBranch:       "feature/task",
		SHA256:               "policy-digest",
		Requirements: Requirements{
			RequireLinkedWorktree: true,
			RequirePullRequest:    true,
			BlockForcePush:        true,
			RequiredStatusChecks:  true,
		},
	}
	github := fakeGitHub{
		metadata: Metadata{ID: 123456, FullName: "acme/widget", DefaultBranch: "main"},
		branches: map[string]BranchMetadata{
			"feature/task": {Name: "feature/task", Protected: false},
			"main":         {Name: "main", Protected: true},
		},
		rules: map[string]map[string]bool{
			"feature/task": {},
			"main": {
				"pull_request":           true,
				"non_fast_forward":       true,
				"required_status_checks": true,
			},
		},
		branchErr:  map[string]error{},
		rulesError: map[string]error{},
	}
	action := policy.Action{Tool: "Write", CWD: worktree, Target: filepath.Join(worktree, "new.txt")}
	report, err := Assess(context.Background(), action, config, git, github, time.Unix(1_000, 0))
	if err != nil || report.State != "READY" || !report.LinkedWorktree {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	publicationAction := policy.Action{
		Tool: "exec", CWD: worktree,
		Input: map[string]any{"command": "git push origin HEAD:refs/heads/feature/task"},
	}
	publicationReport, err := AssessPublication(
		context.Background(), publicationAction, config, git, github, time.Unix(1_001, 0),
	)
	if err != nil || publicationReport.State != "READY" || !publicationReport.LinkedWorktree || publicationReport.MutationTarget != "" {
		t.Fatalf("publication report=%+v err=%v", publicationReport, err)
	}
}

func runTestGit(t *testing.T, gitPath string, args ...string) {
	t.Helper()
	command := exec.Command(gitPath, args...)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, output)
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
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "repository_identity=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessBlocksDefaultBranchAndControlCheckout(t *testing.T) {
	root, config, git, github := readyInputs(t)
	git["rev-parse --abbrev-ref HEAD"] = "main"
	config.ExpectedBranch = "main"
	git["rev-parse --absolute-git-dir"] = git["rev-parse --path-format=absolute --git-common-dir"]
	config.ExpectedGitDir = git["rev-parse --absolute-git-dir"]
	config.ExpectedGitCommonDir = git["rev-parse --path-format=absolute --git-common-dir"]
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" {
		t.Fatalf("report=%+v err=%v", report, err)
	}
	if !strings.Contains(report.Summary(), "linked_worktree=fail") || !strings.Contains(report.Summary(), "default_branch=fail") {
		t.Fatalf("missing branch/worktree denial: %s", report.Summary())
	}
}

func TestAssessBlocksMissingRequiredRule(t *testing.T) {
	root, config, git, github := readyInputs(t)
	delete(github.rules["main"], "required_status_checks")
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "required_status_checks=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessPreservesUnknownAndFailsClosedOnGitHubError(t *testing.T) {
	root, config, git, github := readyInputs(t)
	github.rulesError["main"] = errors.New("HTTP 403")
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
	if err == nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "github_rules=unknown") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessBindsTrustedWorktreeGitDirectoriesAndBranch(t *testing.T) {
	for _, mutate := range []func(*Config, fakeGit){
		func(config *Config, _ fakeGit) { config.ExpectedWorktreeRoot = t.TempDir() },
		func(config *Config, _ fakeGit) { config.ExpectedGitDir = t.TempDir() },
		func(config *Config, _ fakeGit) { config.ExpectedGitCommonDir = t.TempDir() },
		func(config *Config, _ fakeGit) { config.ExpectedBranch = "feature/other" },
	} {
		root, config, git, github := readyInputs(t)
		mutate(config, git)
		report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
		if err != nil || report.State != "BLOCKED" {
			t.Fatalf("report=%+v err=%v", report, err)
		}
	}
}

func TestAssessRejectsUnboundAndOutsideMutationTargets(t *testing.T) {
	root, config, git, github := readyInputs(t)
	for _, action := range []policy.Action{
		{Tool: "exec", Command: "touch changed", CWD: root},
		{Tool: "Write", CWD: root},
		{Tool: "Write", Command: "pwd", CWD: root, Target: filepath.Join(root, "README.md")},
		{Tool: "Write", CWD: root, Target: filepath.Join(filepath.Dir(root), "outside")},
	} {
		report, err := Assess(context.Background(), action, config, git, github, time.Now())
		if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "mutation_target=fail") {
			t.Fatalf("action=%+v report=%+v err=%v", action, report, err)
		}
	}
}

func TestAssessRejectsMutationThroughEscapingSymlink(t *testing.T) {
	root, config, git, github := readyInputs(t)
	outside := t.TempDir()
	link := filepath.Join(root, "escape")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	action := policy.Action{Tool: "Write", CWD: root, Target: filepath.Join(link, "new-file")}
	report, err := Assess(context.Background(), action, config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "mutation_target=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessRejectsProtectedExpectedBranch(t *testing.T) {
	root, config, git, github := readyInputs(t)
	config.ExpectedBranch = "release"
	git["rev-parse --abbrev-ref HEAD"] = "release"
	github.rules["release"] = map[string]bool{"required_status_checks": true}
	report, err := Assess(context.Background(), policy.Action{Tool: "Write", CWD: root, Target: filepath.Join(root, "README.md")}, config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "protected_branch=fail") {
		t.Fatalf("report=%+v err=%v", report, err)
	}
}

func TestAssessRejectsGitHubRepositoryIDMismatch(t *testing.T) {
	root, config, git, github := readyInputs(t)
	github.metadata.ID++
	report, err := Assess(context.Background(), mutationAction(root), config, git, github, time.Now())
	if err != nil || report.State != "BLOCKED" || !strings.Contains(report.Summary(), "github_repository_id=fail") {
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
