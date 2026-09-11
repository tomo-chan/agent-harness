// agent-harness is the S1 generic JSON hook, not a command executor.
package main

import (
	"os"

	"github.com/tomo-chan/agent-harness/internal/trustedexec"
)

func main() { os.Exit(trustedexec.Run(os.Stdin, os.Stdout, os.Args[1:])) }
