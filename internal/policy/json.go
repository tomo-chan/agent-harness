package policy

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"unicode/utf8"
)

// MaxJSON bounds policy and hook input independently. Depth is also bounded.
const MaxJSON = 1 << 20

// Object rejects duplicate keys (including nested keys), trailing JSON and
// non-object roots. encoding/json's last-key-wins behavior is inappropriate here.
func Object(r io.Reader) (map[string]any, error) {
	b, err := io.ReadAll(io.LimitReader(r, MaxJSON+1))
	if err != nil {
		return nil, err
	}
	if len(b) > MaxJSON {
		return nil, fmt.Errorf("JSON exceeds size limit")
	}
	if !utf8.Valid(b) {
		return nil, fmt.Errorf("invalid UTF-8")
	}
	return objectBytes(b)
}

func objectBytes(b []byte) (map[string]any, error) {
	// UseNumber avoids accepting overflowing or rounded numeric metadata.
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	v, err := value(d, 0)
	if err != nil {
		return nil, err
	}
	if _, err = d.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing JSON")
	}
	m, ok := v.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("JSON must be an object")
	}
	return m, nil
}

func value(d *json.Decoder, depth int) (any, error) {
	if depth > 64 {
		return nil, fmt.Errorf("JSON exceeds depth limit")
	}
	t, err := d.Token()
	if err != nil {
		return nil, err
	}
	switch t {
	case json.Delim('{'):
		m := map[string]any{}
		for d.More() {
			k, err := d.Token()
			if err != nil {
				return nil, err
			}
			key, ok := k.(string)
			if !ok {
				return nil, fmt.Errorf("invalid key")
			}
			if _, exists := m[key]; exists {
				return nil, fmt.Errorf("duplicate key")
			}
			v, err := value(d, depth+1)
			if err != nil {
				return nil, err
			}
			m[key] = v
		}
		_, err = d.Token()
		return m, err
	case json.Delim('['):
		a := []any{}
		for d.More() {
			v, err := value(d, depth+1)
			if err != nil {
				return nil, err
			}
			a = append(a, v)
		}
		_, err = d.Token()
		return a, err
	default:
		return t, nil
	}
}
