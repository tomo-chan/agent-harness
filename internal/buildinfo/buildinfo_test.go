package buildinfo

import "testing"

func TestCurrentIncludesPlatformIdentity(t *testing.T) {
	info := Current()
	if info.GoVersion == "" || info.GOOS == "" || info.GOARCH == "" {
		t.Fatalf("incomplete build identity: %+v", info)
	}
}
