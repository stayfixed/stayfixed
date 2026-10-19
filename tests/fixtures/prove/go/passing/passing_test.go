package passing

import "testing"

func TestPasses(t *testing.T) {}

func TestSkipped(t *testing.T) { t.Skip("skipped on purpose") }
