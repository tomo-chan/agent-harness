// Package buildinfo exposes immutable build metadata embedded by the Go toolchain.
// It supports deployment-side source↔binary verification without treating the
// binary's self-report as a signature or independent provenance attestation.
package buildinfo

import (
	"runtime"
	"runtime/debug"
)

type Info struct {
	GoVersion string `json:"go_version"`
	GOOS      string `json:"goos"`
	GOARCH    string `json:"goarch"`
	Module    string `json:"module,omitempty"`
	Revision  string `json:"vcs_revision,omitempty"`
	Modified  string `json:"vcs_modified,omitempty"`
	VCSTime   string `json:"vcs_time,omitempty"`
}

func Current() Info {
	out := Info{GoVersion: runtime.Version(), GOOS: runtime.GOOS, GOARCH: runtime.GOARCH}
	bi, ok := debug.ReadBuildInfo()
	if !ok { return out }
	out.Module = bi.Main.Path
	for _, setting := range bi.Settings {
		switch setting.Key {
		case "vcs.revision": out.Revision = setting.Value
		case "vcs.modified": out.Modified = setting.Value
		case "vcs.time": out.VCSTime = setting.Value
		}
	}
	return out
}
