package controlplane

import (
	"context"
	"errors"
	"testing"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

type fakeGit struct {
	outputs  map[string]string
	failures map[string]error
}

func (g fakeGit) Run(_ context.Context, _ string, args ...string) (string, error) {
	key := stringsJoin(args)
	if err := g.failures[key]; err != nil {
		return "", err
	}
	return g.outputs[key], nil
}

type fakeGitHub struct {
	sha, digest string
	err         error
}

func (g fakeGitHub) BranchHead(context.Context, string, string) (string, string, error) {
	return g.sha, g.digest, g.err
}

func stringsJoin(v []string) string {
	out := ""
	for i, s := range v {
		if i != 0 {
			out += " "
		}
		out += s
	}
	return out
}

func allowed() policy.Decision {
	d := policy.Result("allow", "publication validated", "publication")
	d.Evidence = &policy.Evidence{Publication: &policy.PublicationEvidence{}}
	return d
}

func report() repository.Report {
	return repository.Report{State: "READY", Repository: "tomo-chan/agent-harness", DefaultBranch: "main", Branch: "feature/x", HeadSHA: "head"}
}

func TestIsProtectedPath(t *testing.T) {
	for _, path := range []string{"AGENTS.md", "main.go", "go.mod", "go.sum", "internal/trustedexec/run.go", ".github/workflows/go.yml", "reference/harness/a.go", "./.codex/hooks.json"} {
		if !IsProtectedPath(path) {
			t.Fatalf("expected protected: %s", path)
		}
	}
	for _, path := range []string{"README.md", "docs/design.md", "cmd/example/main.go"} {
		if IsProtectedPath(path) {
			t.Fatalf("unexpected protected: %s", path)
		}
	}
}

func TestEvaluateClearDiffKeepsAllow(t *testing.T) {
	git := fakeGit{outputs: map[string]string{
		"cat-file -e base^{commit}":                    "",
		"diff --no-renames --name-only -z base...head": "README.md\x00docs/design.md\x00",
	}, failures: map[string]error{}}
	got, err := Evaluate(context.Background(), policy.Action{CWD: "/repo"}, allowed(), report(), git, fakeGitHub{sha: "base", digest: "digest"})
	if err != nil || got.Decision != "allow" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
}

func TestEvaluateProtectedDiffRequiresAsk(t *testing.T) {
	git := fakeGit{outputs: map[string]string{
		"cat-file -e base^{commit}":                    "",
		"diff --no-renames --name-only -z base...head": "README.md\x00.github/workflows/go.yml\x00AGENTS.md\x00",
	}, failures: map[string]error{}}
	got, err := Evaluate(context.Background(), policy.Action{CWD: "/repo"}, allowed(), report(), git, fakeGitHub{sha: "base", digest: "digest"})
	if err != nil || got.Decision != "ask" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
	if got.Rule == nil || *got.Rule != "control-plane-publication" {
		t.Fatalf("unexpected rule: %v", got.Rule)
	}
}

func TestEvaluateRenameFromProtectedPathRequiresAsk(t *testing.T) {
	git := fakeGit{outputs: map[string]string{
		"cat-file -e base^{commit}": "",
		// --no-renames reports the source deletion and destination addition.
		"diff --no-renames --name-only -z base...head": ".github/workflows/build.yml\x00safe.txt\x00",
	}, failures: map[string]error{}}
	got, err := Evaluate(context.Background(), policy.Action{CWD: "/repo"}, allowed(), report(), git, fakeGitHub{sha: "base", digest: "digest"})
	if err != nil || got.Decision != "ask" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
}

func TestEvaluateRawNonASCIIProtectedPathRequiresAsk(t *testing.T) {
	git := fakeGit{outputs: map[string]string{
		"cat-file -e base^{commit}":                    "",
		"diff --no-renames --name-only -z base...head": ".github/workflows/日本語\nworkflow.yml\x00",
	}, failures: map[string]error{}}
	got, err := Evaluate(context.Background(), policy.Action{CWD: "/repo"}, allowed(), report(), git, fakeGitHub{sha: "base", digest: "digest"})
	if err != nil || got.Decision != "ask" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
}

func TestEvaluateMissingAuthorityFailsClosed(t *testing.T) {
	got, err := Evaluate(context.Background(), policy.Action{}, allowed(), report(), fakeGit{}, fakeGitHub{err: errors.New("offline")})
	if err == nil || got.Decision != "deny" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
}

func TestEvaluateDoesNotChangeNonAllow(t *testing.T) {
	d := allowed()
	d.Decision = "ask"
	got, err := Evaluate(context.Background(), policy.Action{}, d, repository.Report{}, nil, nil)
	if err != nil || got.Decision != "ask" {
		t.Fatalf("got %v err %v", got.Decision, err)
	}
}
