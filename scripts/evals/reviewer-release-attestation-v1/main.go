// SPDX-License-Identifier: Apache-2.0
// Reviewer release v1 pre/post-run attestation verifier. Build and pin this binary
// outside the evidence bundle before admitting an external release corpus.
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"
)

type envelope struct {
	PayloadBase64   string `json:"payload_base64"`
	SignatureBase64 string `json:"signature_base64"`
}

type artifact struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type payload struct {
	SchemaVersion int                 `json:"schema_version"`
	Phase         string              `json:"phase"`
	ProtocolID    string              `json:"protocol_id"`
	CorpusID      string              `json:"corpus_id"`
	Bindings      map[string]artifact `json:"bindings"`
}

type callInventory struct {
	SchemaVersion int             `json:"schema_version"`
	ProtocolID    string          `json:"protocol_id"`
	CorpusID      string          `json:"corpus_id"`
	Calls         []inventoryCall `json:"calls"`
}

type inventoryCall struct {
	CaseID     string              `json:"case_id"`
	Arm        string              `json:"arm"`
	Repetition int                 `json:"repetition"`
	Artifacts  map[string]artifact `json:"artifacts"`
}

type callKey struct {
	CaseID     string
	Arm        string
	Repetition int
}

type executionReceipt struct {
	PayloadBase64   string `json:"payload_base64"`
	SignatureBase64 string `json:"signature_base64"`
}

type executionEvent struct {
	SchemaVersion  int                 `json:"schema_version"`
	ProtocolID     string              `json:"protocol_id"`
	CorpusID       string              `json:"corpus_id"`
	EventIndex     int                 `json:"event_index"`
	PreviousSHA256 string              `json:"previous_sha256"`
	Stage          string              `json:"stage"`
	CaseID         string              `json:"case_id"`
	Arm            string              `json:"arm"`
	Repetition     int                 `json:"repetition"`
	Artifacts      map[string]artifact `json:"artifacts"`
}

// Python's json.dumps(..., ensure_ascii=False, separators=(",", ":"))
// leaves U+2028/U+2029 unescaped. Go's encoding/json always escapes them, even
// with SetEscapeHTML(false), which would change the frozen arm-order hash.
func pythonJSONString(value string) (string, error) {
	if !utf8.ValidString(value) {
		return "", fmt.Errorf("call-order string is not valid UTF-8")
	}
	var result strings.Builder
	result.WriteByte('"')
	for _, char := range value {
		switch char {
		case '"':
			result.WriteString(`\"`)
		case '\\':
			result.WriteString(`\\`)
		case '\b':
			result.WriteString(`\b`)
		case '\f':
			result.WriteString(`\f`)
		case '\n':
			result.WriteString(`\n`)
		case '\r':
			result.WriteString(`\r`)
		case '\t':
			result.WriteString(`\t`)
		default:
			if char < 0x20 {
				fmt.Fprintf(&result, "\\u%04x", char)
			} else {
				result.WriteRune(char)
			}
		}
	}
	result.WriteByte('"')
	return result.String(), nil
}

func frozenArmMaterial(caseID string, repetition int, arm string) ([]byte, error) {
	quotedCase, err := pythonJSONString(caseID)
	if err != nil {
		return nil, err
	}
	quotedArm, err := pythonJSONString(arm)
	if err != nil {
		return nil, err
	}
	return []byte(fmt.Sprintf(`["reviewer-release-v1",%s,%d,%s]`, quotedCase, repetition, quotedArm)), nil
}

func frozenCallOrder(caseIDs map[string]bool) ([]callKey, error) {
	if len(caseIDs) != 120 {
		return nil, fmt.Errorf("frozen schedule needs 120 committed case IDs")
	}
	ids := make([]string, 0, len(caseIDs))
	for id := range caseIDs {
		if !validCaseID(id) {
			return nil, fmt.Errorf("frozen schedule contains an invalid case ID")
		}
		ids = append(ids, id)
	}
	sort.Strings(ids) // UTF-8 byte order for valid corpus IDs.
	result := make([]callKey, 0, 1080)
	for _, id := range ids {
		for repetition := 1; repetition <= 3; repetition++ {
			type rankedArm struct {
				name string
				hash [32]byte
			}
			arms := make([]rankedArm, 0, 3)
			for _, arm := range []string{"full", "catalog-only", "no-skill"} {
				material, err := frozenArmMaterial(id, repetition, arm)
				if err != nil {
					return nil, fmt.Errorf("cannot encode frozen arm order: %w", err)
				}
				arms = append(arms, rankedArm{arm, sha256.Sum256(material)})
			}
			sort.Slice(arms, func(i, j int) bool {
				comparison := bytes.Compare(arms[i].hash[:], arms[j].hash[:])
				return comparison < 0 || comparison == 0 && arms[i].name < arms[j].name
			})
			for _, arm := range arms {
				result = append(result, callKey{id, arm.name, repetition})
			}
		}
	}
	return result, nil
}

func validCaseID(caseID string) bool {
	return caseID != "" && len(caseID) <= 200 && utf8.ValidString(caseID) && strings.TrimSpace(caseID) == caseID
}

type corpusCommitment struct {
	SchemaVersion int      `json:"schema_version"`
	ProtocolID    string   `json:"protocol_id"`
	CorpusID      string   `json:"corpus_id"`
	Corpus        artifact `json:"corpus"`
	Labels        artifact `json:"labels"`
	Adjudications artifact `json:"adjudications"`
	Custody       artifact `json:"custody"`
}

type evaluatedSkillSnapshot struct {
	SchemaVersion int               `json:"schema_version"`
	ProtocolID    string            `json:"protocol_id"`
	SkillFiles    map[string]string `json:"skill_files"`
	ScannerFiles  map[string]string `json:"scanner_files"`
}

var frozenSkillFiles = []string{
	"skills/e2e-reviewer/SKILL.md",
	"skills/e2e-reviewer/references/review-scope.md",
	"skills/e2e-reviewer/references/scanner-workflow.md",
	"skills/e2e-reviewer/references/semantic-review.md",
	"skills/e2e-reviewer/references/reporting.md",
	"skills/e2e-reviewer/references/pattern-reference.md",
	"skills/e2e-reviewer/references/verification-rules.md",
	"skills/e2e-reviewer/references/grep-patterns.md",
	"skills/e2e-reviewer/references/upstream-rule-sources.md",
	"skills/e2e-reviewer/references/applying-fixes.md",
}

var frozenScannerFiles = []string{
	"scan.sh", "scope-source.sh", "scope-worker.py", "scope-graph.py",
	"scope-lexer.py", "scope-watch.py", "conditional-discovery.py",
}

var requiredBindings = []string{
	"protocol", "evaluated_skill", "corpus_commitment", "runner_image", "model_identity", "isolation_policy",
}

var postRunBindings = []string{
	"protocol", "evaluated_skill", "corpus_commitment", "runner_image", "model_identity",
	"pre_run_attestation", "all_inputs", "raw_outputs", "execution_journal", "response_manifest", "adjudication_ledger", "scorer_output",
}

var sharedBindings = []string{"protocol", "evaluated_skill", "corpus_commitment", "runner_image", "model_identity"}

var inputRoles = []string{"prompt", "staged_case_manifest", "staged_skill_manifest", "runner_config"}
var outputRoles = []string{"codex_jsonl", "stderr", "final_response", "mcp_journal", "transcript_report"}

func strictJSON(data []byte, value any) error {
	if err := rejectDuplicateKeys(data); err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); !errors.Is(err, io.EOF) {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}

func rejectDuplicateKeys(data []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	var walk func() error
	walk = func() error {
		token, err := decoder.Token()
		if err != nil {
			return err
		}
		delim, ok := token.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := make(map[string]bool)
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return err
				}
				key, ok := keyToken.(string)
				if !ok || seen[key] {
					return fmt.Errorf("duplicate or invalid JSON object key")
				}
				seen[key] = true
				if err := walk(); err != nil {
					return err
				}
			}
		case '[':
			for decoder.More() {
				if err := walk(); err != nil {
					return err
				}
			}
		default:
			return fmt.Errorf("invalid JSON delimiter")
		}
		_, err = decoder.Token()
		return err
	}
	if err := walk(); err != nil {
		return err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}

func openRegular(root *os.Root, name string) (*os.File, error) {
	if !fs.ValidPath(name) || strings.Contains(name, "\\") {
		return nil, fmt.Errorf("invalid bundle-relative path %q", name)
	}
	parts := strings.Split(name, "/")
	for index := range parts {
		info, err := root.Lstat(strings.Join(parts[:index+1], "/"))
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, fmt.Errorf("symlink in bundle path %q", name)
		}
		if index < len(parts)-1 && !info.IsDir() {
			return nil, fmt.Errorf("non-directory in bundle path %q", name)
		}
		if index == len(parts)-1 && !info.Mode().IsRegular() {
			return nil, fmt.Errorf("non-regular bundle file %q", name)
		}
	}
	file, err := root.Open(name)
	if err != nil {
		return nil, err
	}
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		file.Close()
		return nil, fmt.Errorf("non-regular opened bundle file %q", name)
	}
	return file, nil
}

func hashFile(root *os.Root, name string) (string, error) {
	file, err := openRegular(root, name)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func readBoundedFile(root *os.Root, name string, limit int64) ([]byte, error) {
	file, err := openRegular(root, name)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || int64(len(data)) > limit || !utf8.Valid(data) {
		return nil, fmt.Errorf("inventory is unreadable, oversized, or invalid UTF-8")
	}
	return data, nil
}

func verifyCorpusCommitment(root *os.Root, bound artifact, corpusID string) (map[string]bool, error) {
	data, err := readBoundedFile(root, bound.Path, 1<<20)
	if err != nil {
		return nil, err
	}
	var commitment corpusCommitment
	if err := strictJSON(data, &commitment); err != nil {
		return nil, fmt.Errorf("invalid corpus commitment: %w", err)
	}
	if commitment.SchemaVersion != 1 || commitment.ProtocolID != "reviewer-release-v1" || commitment.CorpusID != corpusID {
		return nil, fmt.Errorf("corpus commitment identity differs")
	}
	manifestBytes, err := readBoundedFile(root, "bundle.json", 1<<20)
	if err != nil {
		return nil, err
	}
	var manifest map[string]json.RawMessage
	if err := strictJSON(manifestBytes, &manifest); err != nil {
		return nil, fmt.Errorf("invalid bundle manifest: %w", err)
	}
	for name, signedRef := range map[string]artifact{
		"corpus": commitment.Corpus, "labels": commitment.Labels,
		"adjudications": commitment.Adjudications, "custody": commitment.Custody,
	} {
		var bundleRef artifact
		if err := strictJSON(manifest[name], &bundleRef); err != nil {
			return nil, fmt.Errorf("invalid bundle %s reference: %w", name, err)
		}
		if bundleRef != signedRef {
			return nil, fmt.Errorf("signed %s commitment differs from bundle reference", name)
		}
		actual, err := hashFile(root, bundleRef.Path)
		if err != nil || actual != bundleRef.SHA256 {
			return nil, fmt.Errorf("committed %s file hash or path differs", name)
		}
	}
	corpusBytes, err := readBoundedFile(root, commitment.Corpus.Path, 16<<20)
	if err != nil {
		return nil, err
	}
	var corpus map[string]json.RawMessage
	if err := strictJSON(corpusBytes, &corpus); err != nil {
		return nil, fmt.Errorf("invalid committed corpus: %w", err)
	}
	var corpusName string
	if err := strictJSON(corpus["corpus_id"], &corpusName); err != nil || corpusName != corpusID {
		return nil, fmt.Errorf("committed corpus identity differs")
	}
	var cases []struct {
		CaseID string `json:"case_id"`
	}
	if err := json.Unmarshal(corpus["cases"], &cases); err != nil || len(cases) != 120 {
		return nil, fmt.Errorf("committed corpus does not contain 120 cases")
	}
	caseIDs := make(map[string]bool, 120)
	for _, item := range cases {
		if !validCaseID(item.CaseID) || caseIDs[item.CaseID] {
			return nil, fmt.Errorf("committed corpus case IDs are missing or repeated")
		}
		caseIDs[item.CaseID] = true
	}
	return caseIDs, nil
}

func verifyEvaluatedSkill(root *os.Root, bound artifact) error {
	data, err := readBoundedFile(root, bound.Path, 4<<20)
	if err != nil {
		return err
	}
	var snapshot evaluatedSkillSnapshot
	if err := strictJSON(data, &snapshot); err != nil {
		return fmt.Errorf("invalid evaluated skill snapshot: %w", err)
	}
	if snapshot.SchemaVersion != 1 || snapshot.ProtocolID != "reviewer-release-v1" {
		return fmt.Errorf("evaluated skill snapshot identity differs")
	}
	for _, group := range []struct {
		name     string
		actual   map[string]string
		expected []string
	}{
		{"skill", snapshot.SkillFiles, frozenSkillFiles},
		{"scanner", snapshot.ScannerFiles, frozenScannerFiles},
	} {
		if len(group.actual) != len(group.expected) {
			return fmt.Errorf("evaluated %s file set differs", group.name)
		}
		for _, name := range group.expected {
			digest, ok := group.actual[name]
			if !ok || len(digest) != 64 || strings.ToLower(digest) != digest {
				return fmt.Errorf("evaluated %s file hash differs", group.name)
			}
			if _, err := hex.DecodeString(digest); err != nil {
				return fmt.Errorf("evaluated %s file hash is invalid", group.name)
			}
			bundlePath := name
			if group.name == "scanner" {
				bundlePath = "skills/e2e-reviewer/scripts/" + name
			}
			actual, err := hashFile(root, bundlePath)
			if err != nil || actual != digest {
				return fmt.Errorf("evaluated %s file bytes differ from the signed snapshot", group.name)
			}
		}
	}
	return nil
}

func verifyInventory(root *os.Root, bound artifact, corpusID string, expectedCases map[string]bool, roles []string) (map[callKey]map[string]artifact, error) {
	data, err := readBoundedFile(root, bound.Path, 32<<20)
	if err != nil {
		return nil, err
	}
	var inventory callInventory
	if err := strictJSON(data, &inventory); err != nil {
		return nil, fmt.Errorf("invalid call inventory: %w", err)
	}
	if inventory.SchemaVersion != 1 || inventory.ProtocolID != "reviewer-release-v1" || inventory.CorpusID != corpusID || len(inventory.Calls) != 1080 {
		return nil, fmt.Errorf("call inventory identity or 1080-call count differs")
	}
	order, err := frozenCallOrder(expectedCases)
	if err != nil {
		return nil, err
	}
	roleSet := make(map[string]bool, len(roles))
	for _, role := range roles {
		roleSet[role] = true
	}
	seenCalls := make(map[callKey]map[string]artifact, 1080)
	seenCases := make(map[string]bool, 120)
	uniquePaths := make(map[string]bool)
	for index, call := range inventory.Calls {
		if !validCaseID(call.CaseID) ||
			(call.Arm != "full" && call.Arm != "catalog-only" && call.Arm != "no-skill") ||
			call.Repetition < 1 || call.Repetition > 3 || len(call.Artifacts) != len(roles) {
			return nil, fmt.Errorf("invalid call inventory row")
		}
		key := callKey{call.CaseID, call.Arm, call.Repetition}
		if key != order[index] {
			return nil, fmt.Errorf("call inventory differs from frozen order at index %d", index)
		}
		if _, exists := seenCalls[key]; exists {
			return nil, fmt.Errorf("duplicate call inventory row")
		}
		seenCalls[key] = call.Artifacts
		if !expectedCases[call.CaseID] {
			return nil, fmt.Errorf("inventory case ID is absent from committed corpus")
		}
		seenCases[call.CaseID] = true
		rowPaths := make(map[string]bool)
		for role, item := range call.Artifacts {
			if !roleSet[role] || len(item.SHA256) != 64 || rowPaths[item.Path] {
				return nil, fmt.Errorf("invalid or duplicate call artifact")
			}
			rowPaths[item.Path] = true
			if _, err := hex.DecodeString(item.SHA256); err != nil || strings.ToLower(item.SHA256) != item.SHA256 {
				return nil, fmt.Errorf("invalid call artifact SHA-256")
			}
			if role == "prompt" || role == "codex_jsonl" || role == "stderr" || role == "final_response" || role == "mcp_journal" || role == "transcript_report" {
				if uniquePaths[item.Path] {
					return nil, fmt.Errorf("per-call evidence path reused")
				}
				uniquePaths[item.Path] = true
			}
			actual, err := hashFile(root, item.Path)
			if err != nil || actual != item.SHA256 {
				return nil, fmt.Errorf("call artifact %s hash or path differs", role)
			}
		}
	}
	if len(seenCases) != len(expectedCases) {
		return nil, fmt.Errorf("call inventory does not cover 120 cases")
	}
	for caseID := range seenCases {
		for _, arm := range []string{"full", "catalog-only", "no-skill"} {
			for repetition := 1; repetition <= 3; repetition++ {
				if _, exists := seenCalls[callKey{caseID, arm, repetition}]; !exists {
					return nil, fmt.Errorf("call inventory has a missing case/arm/repetition")
				}
			}
		}
	}
	return seenCalls, nil
}

func verifyExecutionJournal(root *os.Root, bound artifact, corpusID string, caseIDs map[string]bool, key ed25519.PublicKey, inputs, outputs map[callKey]map[string]artifact) error {
	data, err := readBoundedFile(root, bound.Path, 16<<20)
	if err != nil {
		return err
	}
	if len(data) == 0 || data[len(data)-1] != '\n' {
		return fmt.Errorf("execution journal must end with a complete row")
	}
	lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
	order, err := frozenCallOrder(caseIDs)
	if err != nil {
		return err
	}
	if len(lines) != 2*len(order) {
		return fmt.Errorf("execution journal must contain one begin and one end receipt per call")
	}
	previous := strings.Repeat("0", 64)
	for index, line := range lines {
		var receipt executionReceipt
		if err := strictJSON(line, &receipt); err != nil {
			return fmt.Errorf("invalid execution receipt %d: %w", index, err)
		}
		payloadBytes, payloadErr := base64.StdEncoding.Strict().DecodeString(receipt.PayloadBase64)
		signature, signatureErr := base64.StdEncoding.Strict().DecodeString(receipt.SignatureBase64)
		if payloadErr != nil || signatureErr != nil || len(signature) != ed25519.SignatureSize || !ed25519.Verify(key, payloadBytes, signature) {
			return fmt.Errorf("invalid execution receipt signature at index %d", index)
		}
		var event executionEvent
		if err := strictJSON(payloadBytes, &event); err != nil {
			return fmt.Errorf("invalid execution event %d: %w", index, err)
		}
		call := order[index/2]
		stage := "begin"
		artifacts := inputs[call]
		if index%2 == 1 {
			stage = "end"
			artifacts = outputs[call]
		}
		if event.SchemaVersion != 1 || event.ProtocolID != "reviewer-release-v1" || event.CorpusID != corpusID ||
			event.EventIndex != index || event.PreviousSHA256 != previous || event.Stage != stage ||
			event.CaseID != call.CaseID || event.Arm != call.Arm || event.Repetition != call.Repetition ||
			len(event.Artifacts) != len(artifacts) {
			return fmt.Errorf("execution event %d differs from frozen schedule or signed inventory", index)
		}
		for role, expected := range artifacts {
			if event.Artifacts[role] != expected {
				return fmt.Errorf("execution event %d artifact %s differs from signed inventory", index, role)
			}
		}
		current := sha256.Sum256(payloadBytes)
		previous = hex.EncodeToString(current[:])
	}
	return nil
}

func verify(bundlePath, attestationPath, publicKeyBase64, protocolSHA256 string) (payload, string, error) {
	return verifyPhase(bundlePath, attestationPath, publicKeyBase64, protocolSHA256, "pre_run")
}

func verifyExecutionEventShape(event executionEvent) error {
	if event.SchemaVersion != 1 || event.ProtocolID != "reviewer-release-v1" || event.CorpusID == "" ||
		event.EventIndex < 0 || event.EventIndex >= 2160 || !validCaseID(event.CaseID) ||
		(event.Arm != "full" && event.Arm != "catalog-only" && event.Arm != "no-skill") || event.Repetition < 1 || event.Repetition > 3 ||
		(event.Stage != "begin" && event.Stage != "end") || (event.Stage == "begin" && event.EventIndex%2 != 0) || (event.Stage == "end" && event.EventIndex%2 != 1) {
		return fmt.Errorf("execution event identity is invalid")
	}
	if len(event.PreviousSHA256) != 64 || strings.ToLower(event.PreviousSHA256) != event.PreviousSHA256 {
		return fmt.Errorf("execution event predecessor hash is invalid")
	}
	if _, err := hex.DecodeString(event.PreviousSHA256); err != nil || event.EventIndex == 0 && event.PreviousSHA256 != strings.Repeat("0", 64) {
		return fmt.Errorf("execution event predecessor hash is invalid")
	}
	roles := inputRoles
	if event.Stage == "end" {
		roles = outputRoles
	}
	if len(event.Artifacts) != len(roles) {
		return fmt.Errorf("execution event artifact roles differ")
	}
	seenPaths := make(map[string]bool, len(roles))
	for _, role := range roles {
		ref, ok := event.Artifacts[role]
		if !ok || !fs.ValidPath(ref.Path) || strings.Contains(ref.Path, "\\") || seenPaths[ref.Path] || len(ref.SHA256) != 64 || strings.ToLower(ref.SHA256) != ref.SHA256 {
			return fmt.Errorf("execution event artifact is invalid")
		}
		if _, err := hex.DecodeString(ref.SHA256); err != nil {
			return fmt.Errorf("execution event artifact hash is invalid")
		}
		seenPaths[ref.Path] = true
	}
	return nil
}

func verifyReceiptFile(receiptPath, publicKeyBase64, expectedPayloadSHA256 string) (string, error) {
	if len(expectedPayloadSHA256) != 64 || strings.ToLower(expectedPayloadSHA256) != expectedPayloadSHA256 {
		return "", fmt.Errorf("invalid expected receipt payload SHA-256")
	}
	if _, err := hex.DecodeString(expectedPayloadSHA256); err != nil {
		return "", fmt.Errorf("invalid expected receipt payload SHA-256")
	}
	key, err := base64.StdEncoding.Strict().DecodeString(publicKeyBase64)
	if err != nil || len(key) != ed25519.PublicKeySize {
		return "", fmt.Errorf("invalid Ed25519 public key")
	}
	if !filepath.IsAbs(receiptPath) {
		return "", fmt.Errorf("receipt path must be absolute")
	}
	parent := filepath.Dir(receiptPath)
	info, err := os.Lstat(parent)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("receipt parent must be a real directory")
	}
	root, err := os.OpenRoot(parent)
	if err != nil {
		return "", err
	}
	defer root.Close()
	receiptBytes, err := readBoundedFile(root, filepath.Base(receiptPath), 16<<10)
	if err != nil {
		return "", fmt.Errorf("receipt is unreadable: %w", err)
	}
	var signed executionReceipt
	if err := strictJSON(receiptBytes, &signed); err != nil {
		return "", fmt.Errorf("invalid receipt envelope: %w", err)
	}
	payloadBytes, err := base64.StdEncoding.Strict().DecodeString(signed.PayloadBase64)
	if err != nil || len(payloadBytes) > 16<<10 || !utf8.Valid(payloadBytes) {
		return "", fmt.Errorf("invalid receipt payload encoding")
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(signed.SignatureBase64)
	if err != nil || len(signature) != ed25519.SignatureSize || !ed25519.Verify(key, payloadBytes, signature) {
		return "", fmt.Errorf("invalid receipt Ed25519 signature")
	}
	digest := sha256.Sum256(payloadBytes)
	actual := hex.EncodeToString(digest[:])
	if actual != expectedPayloadSHA256 {
		return "", fmt.Errorf("receipt payload differs from expected event")
	}
	var event executionEvent
	if err := strictJSON(payloadBytes, &event); err != nil {
		return "", fmt.Errorf("receipt event JSON is invalid: %w", err)
	}
	if err := verifyExecutionEventShape(event); err != nil {
		return "", fmt.Errorf("receipt event identity is invalid")
	}
	return actual, nil
}

func verifyPhase(bundlePath, attestationPath, publicKeyBase64, protocolSHA256, phase string) (payload, string, error) {
	var claim payload
	if phase != "pre_run" && phase != "post_run" {
		return claim, "", fmt.Errorf("unsupported attestation phase")
	}
	if len(protocolSHA256) != 64 {
		return claim, "", fmt.Errorf("invalid frozen protocol SHA-256")
	}
	if _, err := hex.DecodeString(protocolSHA256); err != nil || strings.ToLower(protocolSHA256) != protocolSHA256 {
		return claim, "", fmt.Errorf("invalid frozen protocol SHA-256")
	}
	key, err := base64.StdEncoding.Strict().DecodeString(publicKeyBase64)
	if err != nil || len(key) != ed25519.PublicKeySize {
		return claim, "", fmt.Errorf("invalid Ed25519 public key")
	}
	bundlePath, err = filepath.Abs(bundlePath)
	if err != nil {
		return claim, "", err
	}
	attestationPath, err = filepath.Abs(attestationPath)
	if err != nil {
		return claim, "", err
	}
	relative, err := filepath.Rel(bundlePath, attestationPath)
	if err != nil || !fs.ValidPath(filepath.ToSlash(relative)) {
		return claim, "", fmt.Errorf("attestation must be inside bundle")
	}
	root, err := os.OpenRoot(bundlePath)
	if err != nil {
		return claim, "", err
	}
	defer root.Close()
	attestationFile, err := openRegular(root, filepath.ToSlash(relative))
	if err != nil {
		return claim, "", err
	}
	attestationBytes, err := io.ReadAll(io.LimitReader(attestationFile, 1<<20+1))
	attestationFile.Close()
	if err != nil || len(attestationBytes) > 1<<20 || !utf8.Valid(attestationBytes) {
		return claim, "", fmt.Errorf("attestation is unreadable, oversized, or invalid UTF-8")
	}
	attestationHash := sha256.Sum256(attestationBytes)
	var signed envelope
	if err := strictJSON(attestationBytes, &signed); err != nil {
		return claim, "", fmt.Errorf("invalid attestation envelope: %w", err)
	}
	payloadBytes, err := base64.StdEncoding.Strict().DecodeString(signed.PayloadBase64)
	if err != nil || !utf8.Valid(payloadBytes) {
		return claim, "", fmt.Errorf("invalid payload base64 or UTF-8")
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(signed.SignatureBase64)
	if err != nil || len(signature) != ed25519.SignatureSize || !ed25519.Verify(key, payloadBytes, signature) {
		return claim, "", fmt.Errorf("invalid Ed25519 signature")
	}
	if err := strictJSON(payloadBytes, &claim); err != nil {
		return claim, "", fmt.Errorf("invalid signed payload: %w", err)
	}
	if claim.SchemaVersion != 1 || claim.Phase != phase || claim.ProtocolID != "reviewer-release-v1" || claim.CorpusID == "" {
		return claim, "", fmt.Errorf("invalid %s identity", phase)
	}
	bindings := requiredBindings
	if phase == "post_run" {
		bindings = postRunBindings
	}
	if len(claim.Bindings) != len(bindings) {
		return claim, "", fmt.Errorf("wrong %s binding set", phase)
	}
	seenPaths := make(map[string]bool)
	for _, name := range bindings {
		bound, ok := claim.Bindings[name]
		if !ok || len(bound.SHA256) != 64 || seenPaths[bound.Path] {
			return claim, "", fmt.Errorf("invalid or duplicate %s binding", name)
		}
		seenPaths[bound.Path] = true
		if _, err := hex.DecodeString(bound.SHA256); err != nil || strings.ToLower(bound.SHA256) != bound.SHA256 {
			return claim, "", fmt.Errorf("invalid SHA-256 for %s", name)
		}
		if name == "protocol" && bound.SHA256 != protocolSHA256 {
			return claim, "", fmt.Errorf("signed protocol does not match frozen protocol")
		}
		actual, err := hashFile(root, bound.Path)
		if err != nil {
			return claim, "", fmt.Errorf("artifact %s: %w", name, err)
		}
		if actual != bound.SHA256 {
			return claim, "", fmt.Errorf("artifact mismatch for %s", name)
		}
	}
	if err := verifyEvaluatedSkill(root, claim.Bindings["evaluated_skill"]); err != nil {
		return claim, "", fmt.Errorf("evaluated_skill: %w", err)
	}
	caseIDs, err := verifyCorpusCommitment(root, claim.Bindings["corpus_commitment"], claim.CorpusID)
	if err != nil {
		return claim, "", fmt.Errorf("corpus_commitment: %w", err)
	}
	if phase == "post_run" {
		preRun := claim.Bindings["pre_run_attestation"]
		preClaim, preHash, err := verify(bundlePath, filepath.Join(bundlePath, filepath.FromSlash(preRun.Path)), publicKeyBase64, protocolSHA256)
		if err != nil {
			return claim, "", fmt.Errorf("pre-run attestation chain: %w", err)
		}
		if preHash != preRun.SHA256 || preClaim.CorpusID != claim.CorpusID {
			return claim, "", fmt.Errorf("pre-run attestation identity mismatch")
		}
		for _, name := range sharedBindings {
			if preClaim.Bindings[name].SHA256 != claim.Bindings[name].SHA256 {
				return claim, "", fmt.Errorf("pre/post binding mismatch for %s", name)
			}
		}
		inputs, err := verifyInventory(root, claim.Bindings["all_inputs"], claim.CorpusID, caseIDs, inputRoles)
		if err != nil {
			return claim, "", fmt.Errorf("all_inputs: %w", err)
		}
		outputs, err := verifyInventory(root, claim.Bindings["raw_outputs"], claim.CorpusID, caseIDs, outputRoles)
		if err != nil {
			return claim, "", fmt.Errorf("raw_outputs: %w", err)
		}
		for key := range inputs {
			if _, exists := outputs[key]; !exists {
				return claim, "", fmt.Errorf("input/output call identities differ")
			}
		}
		if err := verifyExecutionJournal(root, claim.Bindings["execution_journal"], claim.CorpusID, caseIDs, key, inputs, outputs); err != nil {
			return claim, "", fmt.Errorf("execution_journal: %w", err)
		}
	}
	return claim, hex.EncodeToString(attestationHash[:]), nil
}

func main() {
	attestation := flag.String("attestation", "", "signed attestation inside bundle")
	bundle := flag.String("bundle", "", "evidence bundle directory")
	publicKey := flag.String("public-key", "", "preregistered Ed25519 public key (base64)")
	protocolSHA256 := flag.String("protocol-sha256", "", "SHA-256 of the frozen protocol passed by the preflight")
	phase := flag.String("phase", "pre_run", "attestation phase: pre_run or post_run")
	receipt := flag.String("receipt", "", "single online execution receipt to verify before proceeding")
	expectedReceiptPayload := flag.String("expected-receipt-payload-sha256", "", "SHA-256 of the exact expected execution event bytes")
	serveWitness := flag.Bool("serve-witness", false, "run an operator-controlled one-shot-sequence witness service")
	privateKey := flag.String("private-key", "", "operator-owned raw Ed25519 private key outside the evidence bundle")
	witnessJournal := flag.String("witness-journal", "", "new private append-only operator journal outside the evidence bundle")
	socket := flag.String("socket", "", "new private Unix socket for witness event requests")
	socketGID := flag.Int("socket-gid", -1, "dedicated runner-access group ID for the witness socket")
	runnerUID := flag.Int("runner-uid", -1, "non-root user ID of the separate model runner")
	artifactGID := flag.Int("artifact-gid", -1, "dedicated read-only artifact group shared with the runner")
	flag.Parse()
	if *serveWitness {
		if flag.NArg() != 0 || *receipt != "" || *expectedReceiptPayload != "" || *phase != "pre_run" || *bundle == "" || *attestation == "" || *publicKey == "" || *protocolSHA256 == "" || *privateKey == "" || *witnessJournal == "" || *socket == "" || *socketGID < 0 || *runnerUID < 0 || *artifactGID < 0 {
			fmt.Fprintln(os.Stderr, "witness mode requires the signed pre-run attestation, bundle, protocol digest, public and private keys, new journal, new socket, and separate runner/artifact identities")
			os.Exit(2)
		}
		service, err := newWitnessService(*bundle, *attestation, *protocolSHA256, *publicKey, *privateKey, *witnessJournal, *runnerUID, *artifactGID)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		defer service.close()
		if err := service.serve(*socket, *socketGID); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if *privateKey != "" || *witnessJournal != "" || *socket != "" || *socketGID != -1 || *runnerUID != -1 || *artifactGID != -1 {
		fmt.Fprintln(os.Stderr, "operator witness options require --serve-witness")
		os.Exit(2)
	}
	if *receipt != "" || *expectedReceiptPayload != "" {
		if flag.NArg() != 0 || *receipt == "" || *expectedReceiptPayload == "" || *publicKey == "" || *attestation != "" || *bundle != "" || *protocolSHA256 != "" || *phase != "pre_run" {
			fmt.Fprintln(os.Stderr, "receipt mode requires --receipt, --expected-receipt-payload-sha256, and --public-key only")
			os.Exit(2)
		}
		digest, err := verifyReceiptFile(*receipt, *publicKey, *expectedReceiptPayload)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if err := json.NewEncoder(os.Stdout).Encode(struct {
			Verified      bool   `json:"verified"`
			Phase         string `json:"phase"`
			PayloadSHA256 string `json:"payload_sha256"`
		}{true, "receipt", digest}); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if flag.NArg() != 0 || *attestation == "" || *bundle == "" || *publicKey == "" || *protocolSHA256 == "" {
		fmt.Fprintln(os.Stderr, "required: --attestation, --bundle, --public-key, --protocol-sha256")
		os.Exit(2)
	}
	claim, digest, err := verifyPhase(*bundle, *attestation, *publicKey, *protocolSHA256, *phase)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	result := struct {
		Verified          bool   `json:"verified"`
		Phase             string `json:"phase"`
		ProtocolID        string `json:"protocol_id"`
		CorpusID          string `json:"corpus_id"`
		AttestationSHA256 string `json:"attestation_sha256"`
	}{true, claim.Phase, claim.ProtocolID, claim.CorpusID, digest}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
