package trustedexec

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTrustedPaths(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	exe := filepath.Join(root, "agent-harness")
	p := filepath.Join(root, "policy.json")
	for _, f := range []string{exe, p} {
		if err := os.WriteFile(f, []byte("{}"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if got, err := PolicyPath(exe, root); err != nil || got != p {
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
}

// The fixed adapter must still fail closed if the consumer cannot receive JSON.
type failingWriter struct{}

func (failingWriter) Write(p []byte) (int, error) { return 0, os.ErrPermission }
func TestOutputFailure(t *testing.T) {
	if code := Run(strings.NewReader(`{}`), failingWriter{}, []string{"unexpected"}); code != 2 {
		t.Fatalf("got %d", code)
	}
}
