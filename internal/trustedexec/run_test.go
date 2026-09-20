package trustedexec

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

func testRepositoryPolicy(t *testing.T, root string) string {
	t.Helper()
	b, err := json.Marshal(map[string]any{
		"schema_version":          1,
		"authority_source":        repository.AuthoritySourceGitHubRules,
		"expected_repository":     "acme/widget",
		"expected_repository_id":  123456,
		"expected_worktree_root":  root,
		"expected_git_dir":        root,
		"expected_git_common_dir": root,
		"expected_branch":         "feature/task",
	})
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestTrustedPaths(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(root, "agent-harness")
	p := filepath.Join(root, "policy.json")
	repositoryPolicy := filepath.Join(root, repository.ConfigFilename)
	for _, f := range []string{exe, p, repositoryPolicy} {
		if err := os.WriteFile(f, []byte("{}"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if got, err := PolicyPath(exe, root); err != nil || got != p {
		t.Fatalf("%s %v", got, err)
	}
	if got, err := RepositoryPolicyPath(exe, root); err != nil || got != repositoryPolicy {
		t.Fatalf("%s %v", got, err)
	}
	for _, configured := range []string{"", ".", t.TempDir(), root + "-prefix"} {
		if _, err := PolicyPath(exe, configured); err == nil {
			t.Fatalf("accepted %s", configured)
		}
	}
	link := filepath.Join(t.TempDir(), "agent-harness")
	if err := os.Symlink(exe, link); err != nil {
		t.Fatal(err)
	}
	if _, err := PolicyPath(link, filepath.Dir(link)); err == nil {
		t.Fatal("symlink location treated as authority")
	}
	if _, err := PolicyPath(link, root); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(p); err != nil {
		t.Fatal(err)
	}
	if _, err := PolicyPath(exe, root); err == nil {
		t.Fatal("missing policy accepted")
	}
	outside := filepath.Join(t.TempDir(), "policy.json")
	if err := os.WriteFile(outside, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, p); err != nil {
		t.Fatal(err)
	}
	if _, err := PolicyPath(exe, root); err == nil {
		t.Fatal("outside symlink accepted")
	}
	if err := os.Remove(p); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(p, 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := PolicyPath(exe, root); err == nil {
		t.Fatal("directory policy accepted")
	}
	if err := os.Remove(repositoryPolicy); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, repositoryPolicy); err != nil {
		t.Fatal(err)
	}
	if _, err := RepositoryPolicyPath(exe, root); err == nil {
		t.Fatal("outside repository policy symlink accepted")
	}
}

func TestRuntimeAppliesRepositoryAuthorityInActualEvaluationPath(t *testing.T) {
	root := t.TempDir()
	executable := filepath.Join(root, "agent-harness")
	for name, contents := range map[string]string{
		"agent-harness":           "binary",
		"policy.json":             `{"default":"ask"}`,
		repository.ConfigFilename: testRepositoryPolicy(t, root),
	} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(contents), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	called := false
	rt := runtime{
		executable: func() (string, error) { return executable, nil },
		getenv: func(name string) string {
			if name == "AGENT_HARNESS_TRUSTED_ROOT" {
				return root
			}
			return ""
		},
		authority: func(_ context.Context, action policy.Action, config *repository.Config) (repository.Report, error) {
			called = true
			if action.CWD != root || action.Target != "README.md" || config.ExpectedRepository != "acme/widget" {
				t.Fatalf("unexpected authority input: action=%+v config=%+v", action, config)
			}
			return repository.Report{
				State:          "BLOCKED",
				Repository:     "acme/widget",
				RepositoryID:   123456,
				RepoRoot:       root,
				MutationTarget: filepath.Join(root, "README.md"),
				Branch:         "main",
				HeadSHA:        strings.Repeat("a", 40),
				Checks:         []repository.Check{{Name: "default_branch", Status: "fail", Detail: "prohibited"}},
				Evidence: repository.Evidence{
					RepositoryPolicySHA256:       config.SHA256,
					AuthoritySource:              repository.AuthoritySourceGitHubBranchMetadata,
					GitHubCurrentAuthoritySHA256: strings.Repeat("b", 64),
					CheckedAt:                    time.Unix(1_000, 0).UTC().Format(time.RFC3339Nano),
				},
			}, nil
		},
	}
	var output bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"Write","input":{"path":"README.md"},"cwd":"`+root+`"}`), &output, nil)
	var decision policy.Decision
	if err := json.Unmarshal(output.Bytes(), &decision); err != nil {
		t.Fatal(err)
	}
	if code != 0 || !called || decision.Decision != "deny" || decision.Rule == nil || *decision.Rule != "repository-authority" {
		t.Fatalf("decision=%+v code=%d called=%t", decision, code, called)
	}
	if decision.Evidence == nil || decision.Evidence.Repository == nil ||
		decision.Evidence.Repository.PolicySHA256 == "" ||
		decision.Evidence.Repository.RepositoryID != 123456 ||
		decision.Evidence.Repository.MutationTarget != filepath.Join(root, "README.md") ||
		decision.Evidence.Repository.AuthoritySource != repository.AuthoritySourceGitHubBranchMetadata ||
		decision.Evidence.Repository.CurrentAuthoritySHA256 != strings.Repeat("b", 64) {
		t.Fatalf("repository evidence missing: %+v", decision)
	}
}

func TestRuntimeAuthorityFailurePreservesUnknownEvidenceAndExitsTwo(t *testing.T) {
	root := t.TempDir()
	executable := filepath.Join(root, "agent-harness")
	for name, contents := range map[string]string{
		"agent-harness":           "binary",
		"policy.json":             `{"default":"allow"}`,
		repository.ConfigFilename: testRepositoryPolicy(t, root),
	} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(contents), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	rt := runtime{
		executable: func() (string, error) { return executable, nil },
		getenv: func(name string) string {
			if name == "AGENT_HARNESS_TRUSTED_ROOT" {
				return root
			}
			return ""
		},
		authority: func(_ context.Context, _ policy.Action, config *repository.Config) (repository.Report, error) {
			return repository.Report{
				State:  "BLOCKED",
				Checks: []repository.Check{{Name: "github_rules", Status: "unknown", Detail: "HTTP 403"}},
				Evidence: repository.Evidence{
					RepositoryPolicySHA256: config.SHA256,
					CheckedAt:              time.Unix(1_000, 0).UTC().Format(time.RFC3339Nano),
				},
			}, errors.New("GitHub unavailable")
		},
	}
	var output bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"Write","input":{"path":"README.md"},"cwd":"`+root+`"}`), &output, nil)
	var decision policy.Decision
	if err := json.Unmarshal(output.Bytes(), &decision); err != nil {
		t.Fatal(err)
	}
	if code != 2 || decision.Decision != "deny" || decision.Evidence == nil || decision.Evidence.Repository == nil {
		t.Fatalf("code=%d decision=%+v", code, decision)
	}
	checks := decision.Evidence.Repository.Checks
	if len(checks) != 1 || checks[0].Status != "unknown" {
		t.Fatalf("unknown evidence was not preserved: %+v", checks)
	}
}

// The fixed adapter must still fail closed if the consumer cannot receive JSON.
type failingWriter struct{}

func (failingWriter) Write(p []byte) (int, error) { return 0, os.ErrPermission }
func TestOutputFailure(t *testing.T) {
	if code := Run(strings.NewReader(`{}`), failingWriter{}, []string{"unexpected"}); code != 2 {
		t.Fatalf("got %d", code)
	}
}
