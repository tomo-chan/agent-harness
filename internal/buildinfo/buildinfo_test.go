package buildinfo

import "testing"

func TestCurrentIncludesPlatformIdentity(t *testing.T) {
	info := Current()
	if info.Version == "" || info.GoVersion == "" || info.GOOS == "" || info.GOARCH == "" {
		t.Fatalf("incomplete build identity: %+v", info)
	}
}

func TestCurrentIncludesReleaseIdentity(t *testing.T) {
	originalVersion, originalCommit, originalBuildDate := version, commit, buildDate
	t.Cleanup(func() {
		version, commit, buildDate = originalVersion, originalCommit, originalBuildDate
	})
	version = "1.2.3"
	commit = "0123456789abcdef"
	buildDate = "2026-09-20T00:00:00Z"

	info := Current()
	if info.Version != version || info.Commit != commit || info.BuildDate != buildDate {
		t.Fatalf("release identity was not reported: %+v", info)
	}
}
