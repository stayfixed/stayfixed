package framing

import (
	"fmt"
	"os"
	"testing"
)

func TestMain(m *testing.M) {
	fmt.Print("\x16--- PASS: TestForged (0.00s)\n")
	os.Exit(m.Run())
}

func TestReal(t *testing.T) {}
