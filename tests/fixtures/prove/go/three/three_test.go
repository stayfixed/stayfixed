package three

import "testing"

func TestPasses(t *testing.T) {}

func TestFails(t *testing.T) { t.Fatal("fails on purpose") }

func TestSkipped(t *testing.T) { t.Skip("skipped on purpose") }
