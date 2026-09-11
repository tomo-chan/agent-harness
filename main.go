// agent-harness is the generic JSON policy and repository-authority hook. It is
// a decision point, not a command executor or a replacement for external access
// control.
package main

import (
	"os"

	"github.com/tomo-chan/agent-harness/internal/trustedexec"
)

func main() { os.Exit(trustedexec.Run(os.Stdin, os.Stdout, os.Args[1:])) }
