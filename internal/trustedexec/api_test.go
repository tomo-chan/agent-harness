package trustedexec

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCompletionGatePathRequiresTrustedExecutableGate(t *testing.T) {
	root := t.TempDir()
	exe := filepath.Join(root, "agent-harness")
	policy := filepath.Join(root, "policy.json")
	repositoryPolicy := filepath.Join(root, "repository-security.json")
	gate := filepath.Join(root, "completion-gate")
	for path, mode := range map[string]os.FileMode{exe:0o700,policy:0o600,repositoryPolicy:0o600,gate:0o700} {
		if err := os.WriteFile(path, []byte("x"), mode); err != nil { t.Fatal(err) }
	}
	canonicalGate, err := filepath.EvalSymlinks(gate)
	if err != nil { t.Fatal(err) }
	got, err := CompletionGatePath(exe, root)
	if err != nil || got != canonicalGate { t.Fatalf("got=%q want=%q err=%v", got, canonicalGate, err) }
	if err := os.Chmod(gate, 0o600); err != nil { t.Fatal(err) }
	if _, err := CompletionGatePath(exe, root); err == nil { t.Fatal("non-executable completion gate accepted") }
}
