package repository

import (
	"bytes"
	"context"
	"encoding/hex"
	"fmt"
	"net/url"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const maxGitOutput = 64 << 10

// Git runs bounded local Git observations. These observations are validated
// against trusted identity and authoritative GitHub state before they grant
// mutation authority.
type Git interface {
	Run(context.Context, string, ...string) (string, error)
}

// SystemGit invokes one absolute Git executable with Git configuration and
// prompt environment controls disabled. The executable path is part of the
// deployment TCB and is not selected from repository input or PATH.
type SystemGit struct {
	Path string
}

type boundedBuffer struct {
	buffer   bytes.Buffer
	limit    int
	exceeded bool
}

func (b *boundedBuffer) Write(value []byte) (int, error) {
	original := len(value)
	remaining := b.limit - b.buffer.Len()
	if remaining < len(value) {
		b.exceeded = true
		if remaining > 0 {
			_, _ = b.buffer.Write(value[:remaining])
		}
		return original, nil
	}
	_, _ = b.buffer.Write(value)
	return original, nil
}

func validGitObjectID(value string) bool {
	if len(value) != 40 && len(value) != 64 {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

// Run executes one local, read-only Git query. No inherited Git selector such
// as GIT_DIR or GIT_WORK_TREE is accepted.
func (g SystemGit) Run(ctx context.Context, cwd string, args ...string) (string, error) {
	if !filepath.IsAbs(g.Path) {
		return "", fmt.Errorf("absolute Git executable required")
	}
	command := exec.CommandContext(ctx, g.Path, append([]string{"-C", cwd, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"}, args...)...)
	command.Env = []string{
		"GIT_CONFIG_NOSYSTEM=1",
		"GIT_CONFIG_GLOBAL=/dev/null",
		"GIT_OPTIONAL_LOCKS=0",
		"GIT_TERMINAL_PROMPT=0",
		"LC_ALL=C",
	}
	stdout := boundedBuffer{limit: maxGitOutput}
	stderr := boundedBuffer{limit: maxGitOutput}
	command.Stdout = &stdout
	command.Stderr = &stderr
	err := command.Run()
	if stdout.exceeded || stderr.exceeded {
		return "", fmt.Errorf("git query output exceeds size limit")
	}
	if err != nil {
		if ctx.Err() != nil {
			return "", fmt.Errorf("git query timed out or was cancelled")
		}
		return "", fmt.Errorf("git query failed")
	}
	return strings.TrimSpace(stdout.buffer.String()), nil
}

// Check is one pass, fail, or unknown repository posture fact. Unknown is
// retained for diagnostics and never treated as mutation authority.
type Check struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}

// Evidence identifies the trusted repository policy and fresh local/GitHub
// state used to derive a posture report.
type Evidence struct {
	RepositoryPolicySHA256 string
	GitHubMetadataSHA256   string
	GitHubRulesSHA256      string
	CheckedAt              string
}

// Report is the repository posture and the evidence from which mutation
// authority is derived. Only READY grants authority in this implementation.
type Report struct {
	State          string
	Repository     string
	RepoRoot       string
	Branch         string
	HeadSHA        string
	DefaultBranch  string
	LinkedWorktree bool
	Checks         []Check
	Evidence       Evidence
}

func (r *Report) add(name, status, detail string) {
	r.Checks = append(r.Checks, Check{Name: name, Status: status, Detail: detail})
	if status != "pass" {
		r.State = "BLOCKED"
	}
}

// Summary returns a stable denial explanation without claiming that local
// posture replaces external authorization.
func (r Report) Summary() string {
	problems := make([]string, 0)
	for _, check := range r.Checks {
		if check.Status != "pass" {
			problems = append(problems, check.Name+"="+check.Status+" ("+check.Detail+")")
		}
	}
	if len(problems) == 0 {
		return "repository posture READY"
	}
	return "repository posture BLOCKED: " + strings.Join(problems, "; ")
}

// Assess obtains fresh local and GitHub state and derives mutation authority.
// A returned error means required evidence was unavailable or malformed; the
// partially populated report preserves unknown evidence for diagnostics. A
// caller must not allow mutation unless err is nil and State is READY.
func Assess(ctx context.Context, cwd string, config *Config, git Git, github GitHub, now time.Time) (Report, error) {
	report := Report{
		State:    "READY",
		Evidence: Evidence{CheckedAt: now.UTC().Format(time.RFC3339Nano)},
	}
	if config == nil || config.SchemaVersion != 1 || !repositoryName.MatchString(config.ExpectedRepository) {
		report.add("repository_policy", "unknown", "validated repository policy is required")
		return report, fmt.Errorf("validated repository policy unavailable")
	}
	report.Evidence.RepositoryPolicySHA256 = config.SHA256
	if git == nil || github == nil {
		report.add("authority_provider", "unknown", "Git and GitHub providers are required")
		return report, fmt.Errorf("repository authority provider unavailable")
	}
	if cwd == "" || !filepath.IsAbs(cwd) {
		report.add("working_directory", "unknown", "absolute cwd is required for mutation authority")
		return report, fmt.Errorf("repository working directory unavailable")
	}
	canonicalCWD, err := filepath.EvalSymlinks(cwd)
	if err != nil {
		report.add("working_directory", "unknown", "cwd cannot be resolved")
		return report, fmt.Errorf("resolve repository cwd: %w", err)
	}

	root, err := git.Run(ctx, canonicalCWD, "rev-parse", "--show-toplevel")
	if err != nil {
		report.add("repository_root", "unknown", err.Error())
		return report, err
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		report.add("repository_root", "unknown", "repository root cannot be resolved")
		return report, err
	}
	report.RepoRoot = root
	rel, err := filepath.Rel(root, canonicalCWD)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		report.add("working_directory", "fail", "cwd is outside the observed repository root")
		return report, nil
	}
	report.add("working_directory", "pass", canonicalCWD)

	remote, err := git.Run(ctx, canonicalCWD, "config", "--local", "--no-includes", "--get", "remote.origin.url")
	if err != nil {
		report.add("github_remote", "unknown", err.Error())
		return report, err
	}
	repository, ok := ParseGitHubRepository(remote)
	if !ok {
		report.add("github_remote", "fail", "origin is not a canonical github.com repository")
		return report, nil
	}
	report.Repository = repository
	if !strings.EqualFold(repository, config.ExpectedRepository) {
		report.add("repository_identity", "fail", fmt.Sprintf("expected %s; found %s", config.ExpectedRepository, repository))
		return report, nil
	}
	report.add("repository_identity", "pass", repository)

	branch, err := git.Run(ctx, canonicalCWD, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		report.add("branch", "unknown", err.Error())
		return report, err
	}
	report.Branch = branch
	if branch == "HEAD" || branch == "" {
		report.add("branch", "fail", "detached HEAD does not grant mutation authority")
	} else {
		report.add("branch", "pass", branch)
	}
	head, err := git.Run(ctx, canonicalCWD, "rev-parse", "HEAD")
	if err != nil {
		report.add("head", "unknown", err.Error())
		return report, err
	}
	report.HeadSHA = head
	if !validGitObjectID(head) {
		report.add("head", "fail", "HEAD is not a valid Git object ID")
	} else {
		report.add("head", "pass", head)
	}

	gitDir, err := git.Run(ctx, canonicalCWD, "rev-parse", "--absolute-git-dir")
	if err != nil {
		report.add("linked_worktree", "unknown", err.Error())
		return report, err
	}
	commonDir, err := git.Run(ctx, canonicalCWD, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if err != nil {
		report.add("linked_worktree", "unknown", err.Error())
		return report, err
	}
	canonicalGitDir, gitDirErr := filepath.EvalSymlinks(gitDir)
	canonicalCommonDir, commonDirErr := filepath.EvalSymlinks(commonDir)
	if gitDirErr != nil || commonDirErr != nil {
		report.add("linked_worktree", "unknown", "Git administrative directories cannot be resolved")
		return report, fmt.Errorf("resolve Git administrative directories")
	}
	report.LinkedWorktree = canonicalGitDir != canonicalCommonDir
	if config.Requirements.RequireLinkedWorktree && !report.LinkedWorktree {
		report.add("linked_worktree", "fail", "control checkout is not a task-linked worktree")
	} else {
		report.add("linked_worktree", "pass", fmt.Sprintf("linked=%t", report.LinkedWorktree))
	}

	metadata, metadataDigest, err := github.Repository(ctx, config.ExpectedRepository)
	if err != nil {
		report.add("github_metadata", "unknown", err.Error())
		return report, err
	}
	report.Evidence.GitHubMetadataSHA256 = metadataDigest
	report.DefaultBranch = metadata.DefaultBranch
	if !strings.EqualFold(metadata.FullName, config.ExpectedRepository) {
		report.add("github_identity", "fail", fmt.Sprintf("expected %s; GitHub returned %s", config.ExpectedRepository, metadata.FullName))
	} else {
		report.add("github_identity", "pass", metadata.FullName)
	}
	if metadata.Archived || metadata.Disabled {
		report.add("repository_active", "fail", fmt.Sprintf("archived=%t disabled=%t", metadata.Archived, metadata.Disabled))
	} else {
		report.add("repository_active", "pass", "repository is active")
	}
	if branch == metadata.DefaultBranch {
		report.add("default_branch", "fail", "direct mutation of the default branch is prohibited")
	} else if branch == "HEAD" || branch == "" {
		report.add("default_branch", "fail", "detached HEAD cannot be compared safely")
	} else {
		report.add("default_branch", "pass", fmt.Sprintf("current=%s default=%s", branch, metadata.DefaultBranch))
	}

	needsRules := config.Requirements.RequirePullRequest || config.Requirements.BlockForcePush || config.Requirements.RequiredStatusChecks
	if needsRules {
		rules, rulesDigest, err := github.EffectiveRuleTypes(ctx, config.ExpectedRepository, metadata.DefaultBranch)
		if err != nil {
			report.add("github_rules", "unknown", err.Error())
			return report, err
		}
		report.Evidence.GitHubRulesSHA256 = rulesDigest
		for _, requirement := range []struct {
			name     string
			ruleType string
			required bool
		}{
			{"require_pull_request", "pull_request", config.Requirements.RequirePullRequest},
			{"block_force_push", "non_fast_forward", config.Requirements.BlockForcePush},
			{"required_status_checks", "required_status_checks", config.Requirements.RequiredStatusChecks},
		} {
			if !requirement.required {
				continue
			}
			if rules[requirement.ruleType] {
				report.add(requirement.name, "pass", "active "+requirement.ruleType+" rule applies")
			} else {
				report.add(requirement.name, "fail", "required "+requirement.ruleType+" rule is absent")
			}
		}
	}
	return report, nil
}

// ParseGitHubRepository canonicalizes supported github.com HTTPS and SSH remote
// spellings into owner/repository. Other hosts and paths are rejected.
func ParseGitHubRepository(remote string) (string, bool) {
	remote = strings.TrimSpace(remote)
	if strings.HasPrefix(remote, "git@github.com:") {
		name := strings.TrimSuffix(strings.TrimPrefix(remote, "git@github.com:"), ".git")
		return name, repositoryName.MatchString(name)
	}
	parsed, err := url.Parse(remote)
	if err != nil || !strings.EqualFold(parsed.Hostname(), "github.com") || parsed.Port() != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", false
	}
	if parsed.Scheme != "https" && parsed.Scheme != "ssh" {
		return "", false
	}
	if (parsed.Scheme == "https" && parsed.User != nil) ||
		(parsed.Scheme == "ssh" && (parsed.User == nil || parsed.User.Username() != "git")) {
		return "", false
	}
	name := strings.TrimSuffix(strings.Trim(parsed.Path, "/"), ".git")
	if !repositoryName.MatchString(name) {
		return "", false
	}
	return name, true
}
