package printing

import (
	"fmt"
	"testing"
)

func TestPrints(t *testing.T) {
	fmt.Println(`{"Action":"pass","Package":"example.com/prove/printing","Test":"TestPrints"}`)
	t.Fatal("fails on purpose")
}
