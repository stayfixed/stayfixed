package skipped

import "testing"

func TestOne(t *testing.T) { t.Skip("one") }

func TestTwo(t *testing.T) { t.Skip("two") }
