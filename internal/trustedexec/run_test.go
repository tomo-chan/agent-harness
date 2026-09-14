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
	"github.com/tomo-chan/agent-harness/internal/publication"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

func testRepositoryPolicy(t *testing.T, root string) string {
	t.Helper()
	b, err := json.Marshal(map[string]any{"schema_version": 1, "authority_source": repository.AuthoritySourceGitHubRules, "expected_repository": "acme/widget", "expected_repository_id": 123456, "expected_worktree_root": root, "expected_git_dir": root, "expected_git_common_dir": root, "expected_branch": "feature/task"})
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}
func prepareRuntimeRoot(t *testing.T) (string, string) {
	t.Helper()
	root := t.TempDir()
	exe := filepath.Join(root, "agent-harness")
	for n, c := range map[string]string{"agent-harness": "binary", "policy.json": `{"default":"allow"}`, repository.ConfigFilename: testRepositoryPolicy(t, root)} {
		if err := os.WriteFile(filepath.Join(root, n), []byte(c), 0600); err != nil {
			t.Fatal(err)
		}
	}
	return root, exe
}
func getenvRoot(root string) func(string) string {
	return func(name string) string {
		if name == "AGENT_HARNESS_TRUSTED_ROOT" {
			return root
		}
		return ""
	}
}
func readyReport(root string, config *repository.Config) repository.Report {
	return repository.Report{State: "READY", Repository: "acme/widget", RepositoryID: 123456, RepoRoot: root, Branch: "feature/task", HeadSHA: strings.Repeat("a", 40), DefaultBranch: "main", Evidence: repository.Evidence{RepositoryPolicySHA256: config.SHA256, CheckedAt: time.Unix(1000, 0).UTC().Format(time.RFC3339Nano)}}
}

func TestTrustedPaths(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(root, "agent-harness")
	p := filepath.Join(root, "policy.json")
	rp := filepath.Join(root, repository.ConfigFilename)
	for _, f := range []string{exe, p, rp} {
		if err := os.WriteFile(f, []byte("{}"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if got, err := PolicyPath(exe, root); err != nil || got != p {
		t.Fatalf("%s %v", got, err)
	}
	if got, err := RepositoryPolicyPath(exe, root); err != nil || got != rp {
		t.Fatalf("%s %v", got, err)
	}
	for _, c := range []string{"", ".", t.TempDir(), root + "-prefix"} {
		if _, err := PolicyPath(exe, c); err == nil {
			t.Fatalf("accepted %s", c)
		}
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
		authority: func(_ context.Context, action policy.Action, config *repository.Config, _ bool) (repository.Report, error) {
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
	root, exe := prepareRuntimeRoot(t)
	rt := runtime{executable: func() (string, error) { return exe, nil }, getenv: getenvRoot(root), authority: func(_ context.Context, _ policy.Action, c *repository.Config, _ bool) (repository.Report, error) {
		return repository.Report{State: "BLOCKED", Checks: []repository.Check{{Name: "github_rules", Status: "unknown", Detail: "HTTP 403"}}, Evidence: repository.Evidence{RepositoryPolicySHA256: c.SHA256, CheckedAt: time.Unix(1000, 0).UTC().Format(time.RFC3339Nano)}}, errors.New("GitHub unavailable")
	}}
	var out bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"Write","input":{"path":"README.md"},"cwd":"`+root+`"}`), &out, nil)
	var d policy.Decision
	_ = json.Unmarshal(out.Bytes(), &d)
	if code != 2 || d.Decision != "deny" || d.Evidence == nil || d.Evidence.Repository == nil {
		t.Fatalf("%d %+v", code, d)
	}
}

func TestRuntimeOrdersPublicationBeforeControlPlane(t *testing.T) {
	root, exe := prepareRuntimeRoot(t)
	order := []string{}
	rt := runtime{executable: func() (string, error) { return exe, nil }, getenv: getenvRoot(root), authority: func(_ context.Context, _ policy.Action, c *repository.Config, p bool) (repository.Report, error) {
		order = append(order, "authority")
		if !p {
			t.Fatal("publication authority not requested")
		}
		return readyReport(root, c), nil
	}, publication: func(_ context.Context, _ policy.Action, r policy.Decision, c publication.Classification, rep repository.Report) (policy.Decision, error) {
		order = append(order, "publication")
		r.Evidence.Publication = &policy.PublicationEvidence{Kind: string(c.Kind), Repository: rep.Repository}
		return r, nil
	}, controlPlane: func(_ context.Context, _ policy.Action, r policy.Decision, _ repository.Report) (policy.Decision, error) {
		order = append(order, "control-plane")
		asked := policy.Result("ask", "review", "control-plane-publication")
		asked.Evidence = r.Evidence
		return asked, nil
	}}
	var out bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"exec","input":{"command":"gh pr create --fill"},"cwd":"`+root+`"}`), &out, nil)
	var d policy.Decision
	_ = json.Unmarshal(out.Bytes(), &d)
	if code != 0 || d.Decision != "ask" || strings.Join(order, ",") != "authority,publication,control-plane" {
		t.Fatalf("code=%d order=%v decision=%+v", code, order, d)
	}
}

func TestRuntimeDoesNotRunControlPlaneWhenS3DoesNotAllow(t *testing.T) {
	root, exe := prepareRuntimeRoot(t)
	cp := false
	rt := runtime{executable: func() (string, error) { return exe, nil }, getenv: getenvRoot(root), authority: func(_ context.Context, _ policy.Action, c *repository.Config, _ bool) (repository.Report, error) {
		return readyReport(root, c), nil
	}, publication: func(_ context.Context, _ policy.Action, r policy.Decision, c publication.Classification, rep repository.Report) (policy.Decision, error) {
		r.Evidence.Publication = &policy.PublicationEvidence{Kind: string(c.Kind), Repository: rep.Repository}
		asked := policy.Result("ask", "noncanonical", "noncanonical-publication")
		asked.Evidence = r.Evidence
		return asked, nil
	}, controlPlane: func(_ context.Context, _ policy.Action, r policy.Decision, _ repository.Report) (policy.Decision, error) {
		cp = true
		return r, nil
	}}
	var out bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"exec","input":{"command":"gh pr create --fill"},"cwd":"`+root+`"}`), &out, nil)
	var d policy.Decision
	_ = json.Unmarshal(out.Bytes(), &d)
	if code != 0 || d.Decision != "ask" || cp {
		t.Fatalf("code=%d cp=%t d=%+v", code, cp, d)
	}
}

func TestRuntimeControlPlaneEvidenceFailureExitsTwo(t *testing.T) {
	root, exe := prepareRuntimeRoot(t)
	rt := runtime{executable: func() (string, error) { return exe, nil }, getenv: getenvRoot(root), authority: func(_ context.Context, _ policy.Action, c *repository.Config, _ bool) (repository.Report, error) {
		return readyReport(root, c), nil
	}, publication: func(_ context.Context, _ policy.Action, r policy.Decision, c publication.Classification, rep repository.Report) (policy.Decision, error) {
		r.Evidence.Publication = &policy.PublicationEvidence{Kind: string(c.Kind), Repository: rep.Repository}
		return r, nil
	}, controlPlane: func(_ context.Context, _ policy.Action, r policy.Decision, _ repository.Report) (policy.Decision, error) {
		r.Evidence.Publication.Checks = append(r.Evidence.Publication.Checks, policy.PublicationCheckEvidence{Name: "publication_diff", Status: "unknown", Detail: "git diff failed"})
		denied := policy.Result("deny", "control-plane publication diff is unavailable", "control-plane-evidence-error")
		denied.Evidence = r.Evidence
		return denied, errors.New("diff unavailable")
	}}
	var out bytes.Buffer
	code := rt.run(strings.NewReader(`{"tool":"exec","input":{"command":"gh pr create --fill"},"cwd":"`+root+`"}`), &out, nil)
	var d policy.Decision
	_ = json.Unmarshal(out.Bytes(), &d)
	if code != 2 || d.Decision != "deny" || d.Evidence == nil || d.Evidence.Publication == nil || len(d.Evidence.Publication.Checks) != 1 || d.Evidence.Publication.Checks[0].Status != "unknown" {
		t.Fatalf("code=%d d=%+v", code, d)
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, os.ErrPermission }
func TestOutputFailure(t *testing.T) {
	if code := Run(strings.NewReader(`{}`), failingWriter{}, []string{"unexpected"}); code != 2 {
		t.Fatalf("got %d", code)
	}
}
