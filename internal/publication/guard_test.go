package publication

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
	"github.com/tomo-chan/agent-harness/internal/repository"
)

const (
	testBranch = "feature/task"
	testHead   = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)

type fakeGit map[string]string

func (f fakeGit) Run(_ context.Context, _ string, args ...string) (string, error) {
	key := strings.Join(args, " ")
	value, ok := f[key]
	if !ok {
		return "", errors.New("unexpected Git query: " + key)
	}
	if strings.HasPrefix(value, "error:") {
		return "", errors.New(strings.TrimPrefix(value, "error:"))
	}
	return value, nil
}

type fakeGitHub struct {
	head   string
	digest string
	err    error
}

func (f fakeGitHub) BranchHead(context.Context, string, string) (string, string, error) {
	return f.head, f.digest, f.err
}

func action(command string) policy.Action {
	return policy.Action{Tool: "exec", Input: map[string]any{"command": command}, CWD: "/work/task"}
}

func candidateDecision(outcome string) policy.Decision {
	rule := "candidate"
	return policy.Decision{
		Decision: outcome,
		Reason:   "candidate",
		Rule:     &rule,
		Evidence: &policy.Evidence{PolicySHA256: strings.Repeat("1", 64), ActionSHA256: strings.Repeat("2", 64)},
	}
}

func readyReport() repository.Report {
	return repository.Report{
		State:         "READY",
		Repository:    "acme/widget",
		Branch:        testBranch,
		HeadSHA:       testHead,
		DefaultBranch: "main",
	}
}

func readyGit() fakeGit {
	return fakeGit{
		"rev-parse --abbrev-ref HEAD":                      testBranch,
		"rev-parse HEAD":                                   testHead,
		"config --no-includes --get-all remote.origin.url": "https://github.com/acme/widget.git",
		"config --no-includes --name-only --list": strings.Join([]string{
			"remote.origin.url",
			"remote.origin.fetch",
			"branch.feature/task.remote",
			"branch.feature/task.merge",
		}, "\n"),
		"remote get-url --push --all origin":                         "git@github.com:acme/widget.git",
		"rev-parse --abbrev-ref --symbolic-full-name @{u}":           "origin/" + testBranch,
		"config --no-includes --bool --get-all remote.origin.mirror": "false",
	}
}

func evaluate(t *testing.T, command string, git fakeGit, github fakeGitHub, environment ...string) (policy.Decision, error) {
	t.Helper()
	act := action(command)
	return Evaluate(
		context.Background(), act, candidateDecision("allow"), Classify(act), readyReport(),
		git, github, environment, time.Unix(1_000, 0),
	)
}

func TestClassifyPublicationMoreBroadlyThanCanonicalForms(t *testing.T) {
	for _, command := range []string{
		"git push origin HEAD:refs/heads/feature/task",
		"git status && git push origin feature/task",
		"env WRAPPED=1 git -c push.default=current push",
		"gh pr create --fill",
		"printf before; gh --repo acme/widget pr create --fill",
	} {
		classification := Classify(action(command))
		if !classification.Candidate {
			t.Errorf("publication was not classified: %q", command)
		}
	}
	if Classify(action("git status")).Candidate {
		t.Fatal("read-only Git command classified as publication")
	}
	if Classify(policy.Action{Tool: "unknown", Input: map[string]any{"command": "git push"}}).Candidate {
		t.Fatal("unknown tool command text treated as an observed shell publication")
	}
}

func TestCanonicalPushBindsTargetAndEvidence(t *testing.T) {
	command := "git push origin HEAD:refs/heads/" + testBranch
	decision, err := evaluate(t, command, readyGit(), fakeGitHub{})
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("decision=%+v err=%v", decision, err)
	}
	evidence := decision.Evidence.Publication
	if evidence == nil || evidence.Kind != string(KindGitPush) || evidence.Repository != "acme/widget" ||
		evidence.Branch != testBranch || evidence.Refspec != "HEAD:refs/heads/"+testBranch ||
		evidence.PushURL != "git@github.com:acme/widget.git" || evidence.Upstream != "origin/"+testBranch ||
		evidence.CheckedAt == "" || len(evidence.Checks) == 0 {
		t.Fatalf("publication evidence is incomplete: %+v", evidence)
	}
}

func TestCanonicalFirstPushRequiresNoExistingUpstream(t *testing.T) {
	command := "git push --set-upstream origin HEAD:refs/heads/" + testBranch
	git := readyGit()
	git["config --no-includes --name-only --list"] = "remote.origin.url\nremote.origin.fetch"
	decision, err := evaluate(t, command, git, fakeGitHub{})
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("decision=%+v err=%v", decision, err)
	}

	decision, err = evaluate(t, command, readyGit(), fakeGitHub{})
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-upstream" {
		t.Fatalf("existing upstream was not denied: decision=%+v err=%v", decision, err)
	}
}

func TestPushRejectsDangerousOrWrongRefspecs(t *testing.T) {
	for _, command := range []string{
		"git push --force origin HEAD:refs/heads/" + testBranch,
		"git push --force-with-lease origin HEAD:refs/heads/" + testBranch,
		"git push --mirror origin",
		"git push origin +HEAD:refs/heads/" + testBranch,
		"git push origin HEAD:refs/heads/main",
		"git push origin HEAD:refs/tags/v1",
		"git push origin HEAD:refs/heads/feature/other",
	} {
		decision, err := evaluate(t, command, readyGit(), fakeGitHub{})
		if err != nil || decision.Decision != "deny" {
			t.Errorf("%q: decision=%+v err=%v", command, decision, err)
		}
	}
}

func TestNoncanonicalAndCompoundPushesAreNotAutonomouslyAllowed(t *testing.T) {
	for _, command := range []string{
		"git push",
		"git push origin feature/task",
		"git status && git push origin HEAD:refs/heads/feature/task",
		"git push origin HEAD:refs/heads/feature/task; printf after",
		"git push origin \"HEAD:refs/heads/feature/task\"",
	} {
		decision, err := evaluate(t, command, readyGit(), fakeGitHub{})
		if err != nil || decision.Decision != "ask" {
			t.Errorf("%q: decision=%+v err=%v", command, decision, err)
		}
	}
}

func TestPushRejectsEffectiveTargetMirrorAndUpstreamMismatch(t *testing.T) {
	tests := []func(fakeGit){
		func(g fakeGit) {
			g["config --no-includes --get-all remote.origin.url"] = "https://github.com/acme/widget.git\nhttps://github.com/other/repository.git"
		},
		func(g fakeGit) { g["remote get-url --push --all origin"] = "https://github.com/other/repository.git" },
		func(g fakeGit) {
			g["remote get-url --push --all origin"] = "https://github.com/acme/widget.git\nhttps://github.com/acme/widget.git"
		},
		func(g fakeGit) {
			g["config --no-includes --name-only --list"] += "\nremote.origin.mirror"
			g["config --no-includes --bool --get-all remote.origin.mirror"] = "true"
		},
		func(g fakeGit) { g["rev-parse --abbrev-ref --symbolic-full-name @{u}"] = "origin/feature/other" },
	}
	for _, mutate := range tests {
		git := readyGit()
		mutate(git)
		decision, err := evaluate(t, "git push origin HEAD:refs/heads/"+testBranch, git, fakeGitHub{})
		if err != nil || decision.Decision != "deny" {
			t.Fatalf("decision=%+v err=%v", decision, err)
		}
	}
}

func TestPushRejectsImplicitFollowTags(t *testing.T) {
	for _, value := range []string{"true", "false\ntrue"} {
		git := readyGit()
		git["config --no-includes --name-only --list"] += "\npush.followTags"
		git["config --no-includes --bool --get-all push.followTags"] = value
		decision, err := evaluate(t, "git push origin HEAD:refs/heads/"+testBranch, git, fakeGitHub{})
		if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-follow-tags" {
			t.Errorf("value=%q decision=%+v err=%v", value, decision, err)
		}
	}

	git := readyGit()
	git["config --no-includes --name-only --list"] += "\npush.followTags"
	git["config --no-includes --bool --get-all push.followTags"] = "false"
	decision, err := evaluate(t, "git push origin HEAD:refs/heads/"+testBranch, git, fakeGitHub{})
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("explicit false was rejected: decision=%+v err=%v", decision, err)
	}

	git = readyGit()
	git["config --no-includes --name-only --list"] += "\npush.followTags"
	git["config --no-includes --bool --get-all push.followTags"] = "error:invalid boolean"
	decision, err = evaluate(t, "git push origin HEAD:refs/heads/"+testBranch, git, fakeGitHub{})
	if err == nil || decision.Decision != "deny" || decision.Evidence.Publication.Checks[len(decision.Evidence.Publication.Checks)-1].Status != "unknown" {
		t.Fatalf("invalid boolean did not fail closed: decision=%+v err=%v", decision, err)
	}
}

func TestPublicationRejectsRepositoryControlledConfigIncludes(t *testing.T) {
	for _, include := range []string{"include.path", "includeIf.gitdir:/work/task.path"} {
		git := readyGit()
		git["config --no-includes --name-only --list"] += "\n" + include
		decision, err := evaluate(t, "git push origin HEAD:refs/heads/"+testBranch, git, fakeGitHub{})
		if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-git-config" {
			t.Errorf("%s: decision=%+v err=%v", include, decision, err)
		}
	}
}

func TestPublicationRejectsTargetChangingEnvironment(t *testing.T) {
	command := "git push origin HEAD:refs/heads/" + testBranch
	for _, selector := range []string{
		"GIT_DIR=/other", "GIT_CONFIG_COUNT=1", "GIT_CONFIG_KEY_0=remote.origin.pushurl",
		"GIT_SSH_COMMAND=evil", "GH_REPO=other/repository", "GH_HOST=evil.invalid", "GH_CONFIG_DIR=/other",
	} {
		decision, err := evaluate(t, command, readyGit(), fakeGitHub{}, selector)
		if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-environment" {
			t.Errorf("%s: decision=%+v err=%v", selector, decision, err)
		}
	}
	decision, err := evaluate(t, command, readyGit(), fakeGitHub{}, "GH_TOKEN=secret", "GIT_TERMINAL_PROMPT=0")
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("non-target selectors were rejected: decision=%+v err=%v", decision, err)
	}
}

func TestCanonicalPRCreateBindsImplicitBaseAndPublishedHead(t *testing.T) {
	decision, err := evaluate(t, "gh pr create --fill", readyGit(), fakeGitHub{head: testHead, digest: "github-ref-digest"})
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("decision=%+v err=%v", decision, err)
	}
	evidence := decision.Evidence.Publication
	if evidence == nil || evidence.PullRequestBase != "main" || evidence.GitHubBranchHeadSHA != testHead ||
		evidence.GitHubBranchSHA256 != "github-ref-digest" || evidence.Upstream != "origin/"+testBranch {
		t.Fatalf("PR evidence is incomplete: %+v", evidence)
	}
}

func TestPRCreateRejectsAllTargetOverrideForms(t *testing.T) {
	for _, command := range []string{
		"gh pr create --repo other/repo --fill",
		"gh pr create --repo=other/repo --fill",
		"gh pr create -Rother/repo --fill",
		"gh -Rother/repo pr create --fill",
		"gh --repo=other/repo pr create --fill",
		"gh pr create --head other --fill",
		"gh pr create --head=other --fill",
		"gh pr create -Hother --fill",
		"gh pr create --base other --fill",
		"gh pr create --base=other --fill",
		"gh pr create -Bother --fill",
	} {
		decision, err := evaluate(t, command, readyGit(), fakeGitHub{})
		if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-pr-target" {
			t.Errorf("%q: decision=%+v err=%v", command, decision, err)
		}
	}
}

func TestPRCreateRejectsRepositoryControlledImplicitBase(t *testing.T) {
	git := readyGit()
	git["config --no-includes --name-only --list"] += "\nbranch.feature/task.gh-merge-base"
	decision, err := evaluate(t, "gh pr create --fill", git, fakeGitHub{head: testHead})
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-pr-base" {
		t.Fatalf("gh-merge-base was not denied: decision=%+v err=%v", decision, err)
	}
}

func TestPRCreateRejectsUnpublishedOrMismatchedHead(t *testing.T) {
	decision, err := evaluate(t, "gh pr create --fill", readyGit(), fakeGitHub{head: strings.Repeat("b", 40), digest: "other"})
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-github-head" {
		t.Fatalf("mismatched GitHub head was not denied: decision=%+v err=%v", decision, err)
	}

	decision, err = evaluate(t, "gh pr create --fill", readyGit(), fakeGitHub{err: errors.New("HTTP 404")})
	if err == nil || decision.Decision != "deny" || decision.Evidence.Publication.Checks[len(decision.Evidence.Publication.Checks)-1].Status != "unknown" {
		t.Fatalf("missing GitHub head did not fail closed: decision=%+v err=%v", decision, err)
	}
}

func TestPublicationKeepsLowerAskAndRejectsStaleRepositoryReport(t *testing.T) {
	act := action("git push origin HEAD:refs/heads/" + testBranch)
	decision, err := Evaluate(
		context.Background(), act, candidateDecision("ask"), Classify(act), readyReport(), readyGit(), fakeGitHub{}, nil, time.Now(),
	)
	if err != nil || decision.Decision != "ask" {
		t.Fatalf("lower ask was elevated: decision=%+v err=%v", decision, err)
	}

	report := readyReport()
	report.State = "BLOCKED"
	decision, err = Evaluate(
		context.Background(), act, candidateDecision("allow"), Classify(act), report, readyGit(), fakeGitHub{}, nil, time.Now(),
	)
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "repository-authority" {
		t.Fatalf("BLOCKED report was accepted: decision=%+v err=%v", decision, err)
	}

	report = readyReport()
	report.Branch = "main"
	decision, err = Evaluate(
		context.Background(), act, candidateDecision("allow"), Classify(act), report, readyGit(), fakeGitHub{}, nil, time.Now(),
	)
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-default-branch" {
		t.Fatalf("default-branch report was accepted: decision=%+v err=%v", decision, err)
	}
}

func TestPublicationDryDecisionInActualLinkedWorktree(t *testing.T) {
	const gitPath = "/usr/bin/git"
	if _, err := os.Stat(gitPath); err != nil {
		t.Skip("production Git path is unavailable on this platform")
	}
	base := t.TempDir()
	control := filepath.Join(base, "control")
	worktree := filepath.Join(base, "task")
	runGit(t, gitPath, "init", control)
	if err := os.WriteFile(filepath.Join(control, "README.md"), []byte("test\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	runGit(t, gitPath, "-C", control, "add", "README.md")
	runGit(t, gitPath, "-C", control, "-c", "user.name=Agent Harness Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial")
	runGit(t, gitPath, "-C", control, "branch", "-M", "main")
	runGit(t, gitPath, "-C", control, "remote", "add", "origin", "https://github.com/acme/widget.git")
	runGit(t, gitPath, "-C", control, "worktree", "add", "-b", testBranch, worktree)
	runGit(t, gitPath, "-C", worktree, "update-ref", "refs/remotes/origin/"+testBranch, "HEAD")
	runGit(t, gitPath, "-C", worktree, "branch", "--set-upstream-to=origin/"+testBranch)

	head := gitOutput(t, gitPath, "-C", worktree, "rev-parse", "HEAD")
	report := readyReport()
	report.HeadSHA = head
	command := "git push origin HEAD:refs/heads/" + testBranch
	action := policy.Action{Tool: "exec", Input: map[string]any{"command": command}, CWD: worktree}
	decision, err := Evaluate(
		context.Background(), action, candidateDecision("allow"), Classify(action), report,
		repository.SystemGit{Path: gitPath}, fakeGitHub{}, nil, time.Unix(1_000, 0),
	)
	if err != nil || decision.Decision != "allow" {
		t.Fatalf("linked-worktree dry push decision=%+v err=%v", decision, err)
	}
	runGit(t, gitPath, "-C", worktree, "config", "push.followTags", "true")
	decision, err = Evaluate(
		context.Background(), action, candidateDecision("allow"), Classify(action), report,
		repository.SystemGit{Path: gitPath}, fakeGitHub{}, nil, time.Unix(1_001, 0),
	)
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-follow-tags" {
		t.Fatalf("linked-worktree followTags decision=%+v err=%v", decision, err)
	}
	runGit(t, gitPath, "-C", worktree, "config", "--unset", "push.followTags")

	runGit(t, gitPath, "-C", worktree, "config", "branch."+testBranch+".gh-merge-base", "release")
	prAction := policy.Action{Tool: "exec", Input: map[string]any{"command": "gh pr create --fill"}, CWD: worktree}
	decision, err = Evaluate(
		context.Background(), prAction, candidateDecision("allow"), Classify(prAction), report,
		repository.SystemGit{Path: gitPath}, fakeGitHub{head: head, digest: "ref-digest"}, nil, time.Unix(1_002, 0),
	)
	if err != nil || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "publication-pr-base" {
		t.Fatalf("linked-worktree gh-merge-base decision=%+v err=%v", decision, err)
	}
}

func runGit(t *testing.T, path string, args ...string) {
	t.Helper()
	command := exec.Command(path, args...)
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v: %s", args, err, output)
	}
}

func gitOutput(t *testing.T, path string, args ...string) string {
	t.Helper()
	command := exec.Command(path, args...)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, output)
	}
	return strings.TrimSpace(string(output))
}
