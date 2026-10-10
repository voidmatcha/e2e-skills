// SPDX-License-Identifier: Apache-2.0

package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func fixture(t *testing.T) (string, string, string, ed25519.PrivateKey, payload) {
	t.Helper()
	bundle := t.TempDir()
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	claim := payload{SchemaVersion: 1, Phase: "pre_run", ProtocolID: "reviewer-release-v1", CorpusID: "external-corpus-001", Bindings: map[string]artifact{}}
	for _, name := range requiredBindings {
		content := []byte(name + " contents")
		if err := os.WriteFile(filepath.Join(bundle, name+".txt"), content, 0600); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(content)
		claim.Bindings[name] = artifact{Path: name + ".txt", SHA256: hex.EncodeToString(digest[:])}
	}
	skillFiles := make(map[string]string, len(frozenSkillFiles))
	for _, name := range frozenSkillFiles {
		path := filepath.Join(bundle, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(name), 0600); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256([]byte(name))
		skillFiles[name] = hex.EncodeToString(digest[:])
	}
	scannerFiles := make(map[string]string, len(frozenScannerFiles))
	for _, name := range frozenScannerFiles {
		path := filepath.Join(bundle, "skills/e2e-reviewer/scripts", name)
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(name), 0600); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256([]byte(name))
		scannerFiles[name] = hex.EncodeToString(digest[:])
	}
	skillBytes, err := json.Marshal(evaluatedSkillSnapshot{
		SchemaVersion: 1, ProtocolID: claim.ProtocolID,
		SkillFiles: skillFiles, ScannerFiles: scannerFiles,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "evaluated_skill.txt"), skillBytes, 0600); err != nil {
		t.Fatal(err)
	}
	skillDigest := sha256.Sum256(skillBytes)
	claim.Bindings["evaluated_skill"] = artifact{Path: "evaluated_skill.txt", SHA256: hex.EncodeToString(skillDigest[:])}
	cases := make([]map[string]string, 120)
	for index := range cases {
		cases[index] = map[string]string{"case_id": fmt.Sprintf("case-%03d", index)}
	}
	corpusBytes, err := json.Marshal(map[string]any{"corpus_id": claim.CorpusID, "cases": cases})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "corpus.json"), corpusBytes, 0600); err != nil {
		t.Fatal(err)
	}
	corpusHash := sha256.Sum256(corpusBytes)
	corpusRef := artifact{Path: "corpus.json", SHA256: hex.EncodeToString(corpusHash[:])}
	refs := map[string]artifact{"corpus": corpusRef}
	for _, name := range []string{"labels", "adjudications", "custody"} {
		content := []byte(name + " sealed before execution")
		path := name + ".json"
		if err := os.WriteFile(filepath.Join(bundle, path), content, 0600); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(content)
		refs[name] = artifact{Path: path, SHA256: hex.EncodeToString(digest[:])}
	}
	bundleBytes, err := json.Marshal(refs)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "bundle.json"), bundleBytes, 0600); err != nil {
		t.Fatal(err)
	}
	commitmentBytes, err := json.Marshal(corpusCommitment{
		SchemaVersion: 1, ProtocolID: claim.ProtocolID, CorpusID: claim.CorpusID,
		Corpus: corpusRef, Labels: refs["labels"], Adjudications: refs["adjudications"], Custody: refs["custody"],
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "corpus_commitment.txt"), commitmentBytes, 0600); err != nil {
		t.Fatal(err)
	}
	commitmentHash := sha256.Sum256(commitmentBytes)
	claim.Bindings["corpus_commitment"] = artifact{Path: "corpus_commitment.txt", SHA256: hex.EncodeToString(commitmentHash[:])}
	return bundle, filepath.Join(bundle, "pre-run-attestation.json"), base64.StdEncoding.EncodeToString(public), private, claim
}

func signFixture(t *testing.T, path string, private ed25519.PrivateKey, claim payload) {
	t.Helper()
	data, err := json.Marshal(claim)
	if err != nil {
		t.Fatal(err)
	}
	signed := envelope{PayloadBase64: base64.StdEncoding.EncodeToString(data), SignatureBase64: base64.StdEncoding.EncodeToString(ed25519.Sign(private, data))}
	encoded, err := json.Marshal(signed)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, encoded, 0600); err != nil {
		t.Fatal(err)
	}
}

func protocolDigest(claim payload) string {
	return claim.Bindings["protocol"].SHA256
}

func inventoryFixture(t *testing.T, bundle, name, corpusID string, roles []string) artifact {
	t.Helper()
	base := filepath.Join(bundle, "evidence", name)
	if err := os.MkdirAll(base, 0700); err != nil {
		t.Fatal(err)
	}
	content := []byte("synthetic per-call artifact")
	digest := sha256.Sum256(content)
	fileHash := hex.EncodeToString(digest[:])
	manifest := callInventory{SchemaVersion: 1, ProtocolID: "reviewer-release-v1", CorpusID: corpusID}
	caseIDs := make(map[string]bool, 120)
	for caseIndex := 0; caseIndex < 120; caseIndex++ {
		caseIDs[fmt.Sprintf("case-%03d", caseIndex)] = true
	}
	order, err := frozenCallOrder(caseIDs)
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range order {
		row := inventoryCall{CaseID: key.CaseID, Arm: key.Arm, Repetition: key.Repetition, Artifacts: map[string]artifact{}}
		for _, role := range roles {
			relative := fmt.Sprintf("evidence/%s/%s-%s-%d-%s.bin", name, key.CaseID, key.Arm, key.Repetition, role)
			if err := os.WriteFile(filepath.Join(bundle, filepath.FromSlash(relative)), content, 0600); err != nil {
				t.Fatal(err)
			}
			row.Artifacts[role] = artifact{Path: relative, SHA256: fileHash}
		}
		manifest.Calls = append(manifest.Calls, row)
	}
	encoded, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	relative := name + ".json"
	if err := os.WriteFile(filepath.Join(bundle, relative), encoded, 0600); err != nil {
		t.Fatal(err)
	}
	manifestHash := sha256.Sum256(encoded)
	return artifact{Path: relative, SHA256: hex.EncodeToString(manifestHash[:])}
}

func executionJournalFixture(t *testing.T, bundle, corpusID string, private ed25519.PrivateKey, inputRef, outputRef artifact) artifact {
	t.Helper()
	readInventory := func(ref artifact) callInventory {
		data, err := os.ReadFile(filepath.Join(bundle, ref.Path))
		if err != nil {
			t.Fatal(err)
		}
		var inventory callInventory
		if err := json.Unmarshal(data, &inventory); err != nil {
			t.Fatal(err)
		}
		return inventory
	}
	inputs, outputs := readInventory(inputRef), readInventory(outputRef)
	if len(inputs.Calls) != 1080 || len(outputs.Calls) != 1080 {
		t.Fatal("fixture inventories are incomplete")
	}
	var journal bytes.Buffer
	previous := strings.Repeat("0", 64)
	for index, input := range inputs.Calls {
		output := outputs.Calls[index]
		for stage, artifacts := range []map[string]artifact{input.Artifacts, output.Artifacts} {
			label := "begin"
			if stage == 1 {
				label = "end"
			}
			event := executionEvent{
				SchemaVersion: 1, ProtocolID: "reviewer-release-v1", CorpusID: corpusID,
				EventIndex: 2*index + stage, PreviousSHA256: previous, Stage: label,
				CaseID: input.CaseID, Arm: input.Arm, Repetition: input.Repetition,
				Artifacts: artifacts,
			}
			payload, err := json.Marshal(event)
			if err != nil {
				t.Fatal(err)
			}
			receipt := executionReceipt{
				PayloadBase64:   base64.StdEncoding.EncodeToString(payload),
				SignatureBase64: base64.StdEncoding.EncodeToString(ed25519.Sign(private, payload)),
			}
			line, err := json.Marshal(receipt)
			if err != nil {
				t.Fatal(err)
			}
			journal.Write(line)
			journal.WriteByte('\n')
			hash := sha256.Sum256(payload)
			previous = hex.EncodeToString(hash[:])
		}
	}
	path := filepath.Join(bundle, "execution_journal.jsonl")
	if err := os.WriteFile(path, journal.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(journal.Bytes())
	return artifact{Path: "execution_journal.jsonl", SHA256: hex.EncodeToString(hash[:])}
}

func postFixture(t *testing.T) (string, string, string, string, ed25519.PrivateKey, payload) {
	t.Helper()
	bundle, prePath, public, private, preClaim := fixture(t)
	signFixture(t, prePath, private, preClaim)
	postClaim := payload{SchemaVersion: 1, Phase: "post_run", ProtocolID: preClaim.ProtocolID, CorpusID: preClaim.CorpusID, Bindings: map[string]artifact{}}
	for _, name := range sharedBindings {
		postClaim.Bindings[name] = preClaim.Bindings[name]
	}
	preBytes, err := os.ReadFile(prePath)
	if err != nil {
		t.Fatal(err)
	}
	preHash := sha256.Sum256(preBytes)
	postClaim.Bindings["pre_run_attestation"] = artifact{Path: filepath.Base(prePath), SHA256: hex.EncodeToString(preHash[:])}
	postClaim.Bindings["all_inputs"] = inventoryFixture(t, bundle, "all_inputs", preClaim.CorpusID, inputRoles)
	postClaim.Bindings["raw_outputs"] = inventoryFixture(t, bundle, "raw_outputs", preClaim.CorpusID, outputRoles)
	postClaim.Bindings["execution_journal"] = executionJournalFixture(t, bundle, preClaim.CorpusID, private, postClaim.Bindings["all_inputs"], postClaim.Bindings["raw_outputs"])
	for _, name := range []string{"response_manifest", "adjudication_ledger", "scorer_output"} {
		content := []byte(name + " contents")
		if err := os.WriteFile(filepath.Join(bundle, name+".txt"), content, 0600); err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(content)
		postClaim.Bindings[name] = artifact{Path: name + ".txt", SHA256: hex.EncodeToString(digest[:])}
	}
	return bundle, prePath, filepath.Join(bundle, "post-run-attestation.json"), public, private, postClaim
}

func TestValidPreRunSignatureAndBindings(t *testing.T) {
	bundle, attestation, public, private, claim := fixture(t)
	signFixture(t, attestation, private, claim)
	verified, digest, err := verify(bundle, attestation, public, protocolDigest(claim))
	if err != nil || verified.CorpusID != claim.CorpusID || len(digest) != 64 {
		t.Fatalf("valid attestation rejected: claim=%+v digest=%q err=%v", verified, digest, err)
	}
	if _, _, err := verify(bundle, attestation, public, strings.Repeat("0", 64)); err == nil || !strings.Contains(err.Error(), "frozen protocol") {
		t.Fatalf("different preflight protocol accepted: %v", err)
	}
}

func TestSignedEvaluatedSkillSnapshotRejectsWrongFileSetAndDigest(t *testing.T) {
	for _, test := range []struct {
		name   string
		change func(*evaluatedSkillSnapshot)
	}{
		{"missing skill", func(snapshot *evaluatedSkillSnapshot) { delete(snapshot.SkillFiles, frozenSkillFiles[0]) }},
		{"extra scanner", func(snapshot *evaluatedSkillSnapshot) {
			snapshot.ScannerFiles["unexpected.py"] = strings.Repeat("0", 64)
		}},
		{"invalid digest", func(snapshot *evaluatedSkillSnapshot) {
			snapshot.SkillFiles[frozenSkillFiles[0]] = strings.Repeat("z", 64)
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			bundle, attestation, public, private, claim := fixture(t)
			path := filepath.Join(bundle, "evaluated_skill.txt")
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var snapshot evaluatedSkillSnapshot
			if err := json.Unmarshal(data, &snapshot); err != nil {
				t.Fatal(err)
			}
			test.change(&snapshot)
			data, err = json.Marshal(snapshot)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(data)
			claim.Bindings["evaluated_skill"] = artifact{Path: "evaluated_skill.txt", SHA256: hex.EncodeToString(digest[:])}
			signFixture(t, attestation, private, claim)
			if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "evaluated_skill") {
				t.Fatalf("signed malformed evaluated skill snapshot accepted: %v", err)
			}
		})
	}
}

func TestTamperingAndWrongKey(t *testing.T) {
	bundle, attestation, public, private, claim := fixture(t)
	signFixture(t, attestation, private, claim)
	if err := os.WriteFile(filepath.Join(bundle, "protocol.txt"), []byte("modified"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "artifact mismatch") {
		t.Fatalf("artifact mutation accepted: %v", err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "protocol.txt"), []byte("protocol contents"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{frozenSkillFiles[0], "skills/e2e-reviewer/scripts/" + frozenScannerFiles[0]} {
		path := filepath.Join(bundle, filepath.FromSlash(name))
		original, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte("changed after signing"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "evaluated_skill") {
			t.Fatalf("evaluated file mutation accepted for %s: %v", name, err)
		}
		if err := os.WriteFile(path, original, 0600); err != nil {
			t.Fatal(err)
		}
	}
	corpusBytes, err := os.ReadFile(filepath.Join(bundle, "corpus.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "corpus.json"), []byte("modified corpus"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "corpus_commitment") {
		t.Fatalf("committed corpus mutation accepted: %v", err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "corpus.json"), corpusBytes, 0600); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"labels", "adjudications", "custody"} {
		path := filepath.Join(bundle, name+".json")
		original, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte("changed after commitment"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "corpus_commitment") {
			t.Fatalf("committed %s mutation accepted: %v", name, err)
		}
		if err := os.WriteFile(path, original, 0600); err != nil {
			t.Fatal(err)
		}
	}
	otherPublic, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := verify(bundle, attestation, base64.StdEncoding.EncodeToString(otherPublic), protocolDigest(claim)); err == nil {
		t.Fatal("wrong signing key accepted")
	}
	data, err := os.ReadFile(attestation)
	if err != nil {
		t.Fatal(err)
	}
	data[len(data)-3] ^= 1
	if err := os.WriteFile(attestation, data, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil {
		t.Fatal("attestation mutation accepted")
	}
}

func TestInvalidSignedPayloads(t *testing.T) {
	for _, test := range []struct {
		name   string
		change func(*payload)
	}{
		{"post-run phase", func(claim *payload) { claim.Phase = "post_run" }},
		{"missing binding", func(claim *payload) { delete(claim.Bindings, "runner_image") }},
		{"extra binding", func(claim *payload) { claim.Bindings["extra"] = claim.Bindings["protocol"] }},
		{"duplicate path", func(claim *payload) { claim.Bindings["runner_image"] = claim.Bindings["protocol"] }},
		{"path traversal", func(claim *payload) {
			claim.Bindings["protocol"] = artifact{Path: "../outside", SHA256: claim.Bindings["protocol"].SHA256}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			bundle, attestation, public, private, claim := fixture(t)
			test.change(&claim)
			signFixture(t, attestation, private, claim)
			if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil {
				t.Fatal("invalid signed payload accepted")
			}
		})
	}
}

func TestSymlinkAndDuplicateJSON(t *testing.T) {
	bundle, attestation, public, private, claim := fixture(t)
	if err := os.Remove(filepath.Join(bundle, "protocol.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(bundle, "evaluated_skill.txt"), filepath.Join(bundle, "protocol.txt")); err != nil {
		t.Fatal(err)
	}
	signFixture(t, attestation, private, claim)
	if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("symlink accepted: %v", err)
	}
	if err := strictJSON([]byte(`{"phase":"pre_run","phase":"post_run"}`), new(map[string]any)); err == nil {
		t.Fatal("duplicate JSON key accepted")
	}
	if err := strictJSON([]byte(`{"payload_base64":"x","signature_base64":"y","unknown":1}`), new(envelope)); err == nil {
		t.Fatal("unknown envelope field accepted")
	}
}

func TestSignedInvalidUTF8PayloadRejected(t *testing.T) {
	bundle, attestation, public, private, claim := fixture(t)
	payloadBytes := []byte{'{', '"', 'x', '"', ':', '"', 0xff, '"', '}'}
	signed := envelope{
		PayloadBase64:   base64.StdEncoding.EncodeToString(payloadBytes),
		SignatureBase64: base64.StdEncoding.EncodeToString(ed25519.Sign(private, payloadBytes)),
	}
	data, err := json.Marshal(signed)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(attestation, data, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := verify(bundle, attestation, public, protocolDigest(claim)); err == nil || !strings.Contains(err.Error(), "UTF-8") {
		t.Fatalf("signed invalid UTF-8 accepted: %v", err)
	}
}

func TestValidPostRunChain(t *testing.T) {
	bundle, _, postPath, public, private, claim := postFixture(t)
	signFixture(t, postPath, private, claim)
	verified, digest, err := verifyPhase(bundle, postPath, public, protocolDigest(claim), "post_run")
	if err != nil || verified.Phase != "post_run" || len(digest) != 64 {
		t.Fatalf("valid post-run chain rejected: claim=%+v digest=%q err=%v", verified, digest, err)
	}
	command := exec.Command("go", "run", "main.go", "witness_service.go", "--phase", "post_run",
		"--attestation", postPath, "--bundle", bundle, "--public-key", public,
		"--protocol-sha256", protocolDigest(claim))
	output, err := command.Output()
	if err != nil {
		t.Fatalf("post-run CLI rejected valid signed evidence: %v", err)
	}
	var result map[string]any
	if err := json.Unmarshal(output, &result); err != nil {
		t.Fatalf("post-run CLI returned invalid JSON: %v", err)
	}
	expected := map[string]any{
		"verified": true, "phase": "post_run", "protocol_id": claim.ProtocolID,
		"corpus_id": claim.CorpusID, "attestation_sha256": digest,
	}
	if !reflect.DeepEqual(result, expected) {
		t.Fatalf("post-run CLI output differs from bridge contract: got=%v want=%v", result, expected)
	}
	wrongPin := exec.Command("go", "run", "main.go", "witness_service.go", "--phase", "post_run",
		"--attestation", postPath, "--bundle", bundle, "--public-key", public,
		"--protocol-sha256", strings.Repeat("0", 64))
	if output, err := wrongPin.Output(); err == nil || len(output) != 0 {
		t.Fatalf("post-run CLI accepted a wrong protocol pin: output=%q err=%v", output, err)
	}
	if _, _, err := verifyPhase(bundle, postPath, public, protocolDigest(claim), "pre_run"); err == nil {
		t.Fatal("post-run attestation accepted as pre-run")
	}
}

func TestFrozenCallOrderMatchesPythonVectors(t *testing.T) {
	ids := make(map[string]bool, 120)
	for index := 0; index < 114; index++ {
		ids[fmt.Sprintf("case-%03d", index)] = true
	}
	ids["é-001"] = true
	ids["<x>&-001"] = true
	ids["line\u2028sep"] = true
	ids["para\u2029sep"] = true
	ids["literal\\u2028"] = true
	ids["control\nline"] = true
	order, err := frozenCallOrder(ids)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		caseID     string
		repetition int
		want       []string
	}{
		{"case-001", 2, []string{"no-skill", "catalog-only", "full"}},
		{"é-001", 1, []string{"no-skill", "full", "catalog-only"}},
		{"<x>&-001", 3, []string{"catalog-only", "no-skill", "full"}},
		{"line\u2028sep", 1, []string{"no-skill", "full", "catalog-only"}},
		{"para\u2029sep", 1, []string{"no-skill", "catalog-only", "full"}},
		{"literal\\u2028", 1, []string{"catalog-only", "full", "no-skill"}},
		{"control\nline", 1, []string{"no-skill", "catalog-only", "full"}},
	} {
		var got []string
		for _, key := range order {
			if key.CaseID == test.caseID && key.Repetition == test.repetition {
				got = append(got, key.Arm)
			}
		}
		if !reflect.DeepEqual(got, test.want) {
			t.Fatalf("%s repetition %d: got %v, want %v", test.caseID, test.repetition, got, test.want)
		}
	}
}

func TestCaseIDContractRejectsLateWitnessFailures(t *testing.T) {
	for _, invalid := range []string{"", "case-001 ", strings.Repeat("x", 201), strings.Repeat("é", 101), "\u3000case-001"} {
		if validCaseID(invalid) {
			t.Fatalf("invalid case ID accepted: %q", invalid)
		}
	}
	if validCaseID(strings.Repeat("é", 100)) == false {
		t.Fatal("exactly 200-byte Unicode case ID rejected")
	}
	ids := make(map[string]bool, 120)
	for index := 0; index < 119; index++ {
		ids[fmt.Sprintf("case-%03d", index)] = true
	}
	ids["case-119 "] = true
	if _, err := frozenCallOrder(ids); err == nil {
		t.Fatal("frozen schedule accepted a case ID the witness would reject")
	}
}

func TestFrozenArmMaterialMatchesPythonJSONBytes(t *testing.T) {
	for _, test := range []struct {
		caseID string
		want   string
	}{
		{"line\u2028sep", "[\"reviewer-release-v1\",\"line\u2028sep\",1,\"full\"]"},
		{"para\u2029sep", "[\"reviewer-release-v1\",\"para\u2029sep\",1,\"full\"]"},
		{`literal\u2028`, `["reviewer-release-v1","literal\\u2028",1,"full"]`},
		{"control\nline", `["reviewer-release-v1","control\nline",1,"full"]`},
		{"\x01<x>&", `["reviewer-release-v1","\u0001<x>&",1,"full"]`},
	} {
		got, err := frozenArmMaterial(test.caseID, 1, "full")
		if err != nil || string(got) != test.want {
			t.Fatalf("case %q: got %q, want %q, err %v", test.caseID, got, test.want, err)
		}
	}
	if _, err := frozenArmMaterial(string([]byte{0xff}), 1, "full"); err == nil {
		t.Fatal("invalid UTF-8 call-order string was accepted")
	}
}

func TestPostRunChainRejectsTampering(t *testing.T) {
	for _, test := range []struct {
		name   string
		change func(t *testing.T, bundle, prePath string, claim *payload)
	}{
		{"different corpus", func(_ *testing.T, _, _ string, claim *payload) { claim.CorpusID = "other-corpus" }},
		{"missing binding", func(_ *testing.T, _, _ string, claim *payload) { delete(claim.Bindings, "raw_outputs") }},
		{"extra binding", func(_ *testing.T, _, _ string, claim *payload) {
			claim.Bindings["extra"] = claim.Bindings["raw_outputs"]
		}},
		{"wrong shared skill", func(t *testing.T, bundle, _ string, claim *payload) {
			content := []byte("different skill")
			if err := os.WriteFile(filepath.Join(bundle, "other-skill.txt"), content, 0600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(content)
			claim.Bindings["evaluated_skill"] = artifact{Path: "other-skill.txt", SHA256: hex.EncodeToString(digest[:])}
		}},
		{"forged pre-run", func(t *testing.T, _, prePath string, _ *payload) {
			if err := os.WriteFile(prePath, []byte("forged"), 0600); err != nil {
				t.Fatal(err)
			}
		}},
		{"wrong-key pre-run", func(t *testing.T, _, prePath string, claim *payload) {
			_, otherPrivate, err := ed25519.GenerateKey(rand.Reader)
			if err != nil {
				t.Fatal(err)
			}
			preClaim := *claim
			preClaim.Phase = "pre_run"
			preClaim.Bindings = make(map[string]artifact)
			for _, name := range requiredBindings {
				if bound, ok := claim.Bindings[name]; ok {
					preClaim.Bindings[name] = bound
				}
			}
			isolationHash := sha256.Sum256([]byte("isolation_policy contents"))
			preClaim.Bindings["isolation_policy"] = artifact{Path: "isolation_policy.txt", SHA256: hex.EncodeToString(isolationHash[:])}
			signFixture(t, prePath, otherPrivate, preClaim)
			data, err := os.ReadFile(prePath)
			if err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(data)
			claim.Bindings["pre_run_attestation"] = artifact{Path: filepath.Base(prePath), SHA256: hex.EncodeToString(digest[:])}
		}},
		{"mutated output", func(t *testing.T, bundle, _ string, _ *payload) {
			if err := os.WriteFile(filepath.Join(bundle, "raw_outputs.json"), []byte("changed"), 0600); err != nil {
				t.Fatal(err)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			bundle, prePath, postPath, public, private, claim := postFixture(t)
			test.change(t, bundle, prePath, &claim)
			signFixture(t, postPath, private, claim)
			if _, _, err := verifyPhase(bundle, postPath, public, protocolDigest(claim), "post_run"); err == nil {
				t.Fatal("invalid post-run chain accepted")
			} else if test.name == "wrong-key pre-run" && !strings.Contains(err.Error(), "invalid Ed25519 signature") {
				t.Fatalf("wrong-key case did not reach the signature check: %v", err)
			}
		})
	}
}

func TestPostRunInventoryRejectsMissingCallAndChangedRawFile(t *testing.T) {
	for _, test := range []struct {
		name   string
		change func(t *testing.T, bundle string, claim *payload)
	}{
		{"missing signed call", func(t *testing.T, bundle string, claim *payload) {
			path := filepath.Join(bundle, claim.Bindings["raw_outputs"].Path)
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var inventory callInventory
			if err := json.Unmarshal(data, &inventory); err != nil {
				t.Fatal(err)
			}
			inventory.Calls = inventory.Calls[:len(inventory.Calls)-1]
			changed, err := json.Marshal(inventory)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, changed, 0600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(changed)
			claim.Bindings["raw_outputs"] = artifact{Path: claim.Bindings["raw_outputs"].Path, SHA256: hex.EncodeToString(digest[:])}
		}},
		{"unknown corpus case", func(t *testing.T, bundle string, claim *payload) {
			path := filepath.Join(bundle, claim.Bindings["raw_outputs"].Path)
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var inventory callInventory
			if err := json.Unmarshal(data, &inventory); err != nil {
				t.Fatal(err)
			}
			inventory.Calls[0].CaseID = "invented-case"
			changed, err := json.Marshal(inventory)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, changed, 0600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(changed)
			claim.Bindings["raw_outputs"] = artifact{Path: claim.Bindings["raw_outputs"].Path, SHA256: hex.EncodeToString(digest[:])}
		}},
		{"reordered signed calls", func(t *testing.T, bundle string, claim *payload) {
			path := filepath.Join(bundle, claim.Bindings["raw_outputs"].Path)
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var inventory callInventory
			if err := json.Unmarshal(data, &inventory); err != nil {
				t.Fatal(err)
			}
			inventory.Calls[0], inventory.Calls[1] = inventory.Calls[1], inventory.Calls[0]
			changed, err := json.Marshal(inventory)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, changed, 0600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(changed)
			claim.Bindings["raw_outputs"] = artifact{Path: claim.Bindings["raw_outputs"].Path, SHA256: hex.EncodeToString(digest[:])}
		}},
		{"mutated raw file", func(t *testing.T, bundle string, claim *payload) {
			path := filepath.Join(bundle, "evidence", "raw_outputs", "case-000-full-1-final_response.bin")
			if err := os.WriteFile(path, []byte("changed raw response"), 0600); err != nil {
				t.Fatal(err)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			bundle, _, postPath, public, private, claim := postFixture(t)
			test.change(t, bundle, &claim)
			signFixture(t, postPath, private, claim)
			if _, _, err := verifyPhase(bundle, postPath, public, protocolDigest(claim), "post_run"); err == nil || !strings.Contains(err.Error(), "raw_outputs") {
				t.Fatalf("invalid raw inventory accepted or rejected at wrong boundary: %v", err)
			}
		})
	}
}

func TestPostRunExecutionJournalRejectsResignedCorruption(t *testing.T) {
	for _, test := range []struct {
		name   string
		change func(t *testing.T, lines [][]byte, private ed25519.PrivateKey) [][]byte
	}{
		{"missing end", func(_ *testing.T, lines [][]byte, _ ed25519.PrivateKey) [][]byte {
			return lines[:len(lines)-1]
		}},
		{"swapped receipts", func(_ *testing.T, lines [][]byte, _ ed25519.PrivateKey) [][]byte {
			lines[0], lines[1] = lines[1], lines[0]
			return lines
		}},
		{"wrong input hash with valid receipt signature", func(t *testing.T, lines [][]byte, private ed25519.PrivateKey) [][]byte {
			var receipt executionReceipt
			if err := json.Unmarshal(lines[0], &receipt); err != nil {
				t.Fatal(err)
			}
			payload, err := base64.StdEncoding.DecodeString(receipt.PayloadBase64)
			if err != nil {
				t.Fatal(err)
			}
			var event executionEvent
			if err := json.Unmarshal(payload, &event); err != nil {
				t.Fatal(err)
			}
			changed := event.Artifacts["prompt"]
			changed.SHA256 = strings.Repeat("0", 64)
			event.Artifacts["prompt"] = changed
			payload, err = json.Marshal(event)
			if err != nil {
				t.Fatal(err)
			}
			receipt.PayloadBase64 = base64.StdEncoding.EncodeToString(payload)
			receipt.SignatureBase64 = base64.StdEncoding.EncodeToString(ed25519.Sign(private, payload))
			lines[0], err = json.Marshal(receipt)
			if err != nil {
				t.Fatal(err)
			}
			return lines
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			bundle, _, postPath, public, private, claim := postFixture(t)
			path := filepath.Join(bundle, claim.Bindings["execution_journal"].Path)
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			lines := bytes.Split(bytes.TrimSuffix(data, []byte("\n")), []byte("\n"))
			lines = test.change(t, lines, private)
			changed := append(bytes.Join(lines, []byte("\n")), '\n')
			if err := os.WriteFile(path, changed, 0600); err != nil {
				t.Fatal(err)
			}
			hash := sha256.Sum256(changed)
			claim.Bindings["execution_journal"] = artifact{Path: claim.Bindings["execution_journal"].Path, SHA256: hex.EncodeToString(hash[:])}
			signFixture(t, postPath, private, claim)
			if _, _, err := verifyPhase(bundle, postPath, public, protocolDigest(claim), "post_run"); err == nil || !strings.Contains(err.Error(), "execution_journal") {
				t.Fatalf("resigned corrupt execution journal accepted or rejected at wrong boundary: %v", err)
			}
		})
	}
}

func TestVerifySingleOnlineReceipt(t *testing.T) {
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	otherPublic, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	key := base64.StdEncoding.EncodeToString(public)
	path := filepath.Join(t.TempDir(), "begin-receipt.json")
	event := executionEvent{
		SchemaVersion: 1, ProtocolID: "reviewer-release-v1", CorpusID: "sealed-corpus",
		EventIndex: 0, PreviousSHA256: strings.Repeat("0", 64), Stage: "begin",
		CaseID: "case-001", Arm: "no-skill", Repetition: 1,
		Artifacts: map[string]artifact{
			"prompt":                {Path: "calls/001/inputs/prompt", SHA256: strings.Repeat("a", 64)},
			"staged_case_manifest":  {Path: "calls/001/inputs/staged_case_manifest", SHA256: strings.Repeat("b", 64)},
			"staged_skill_manifest": {Path: "calls/001/inputs/staged_skill_manifest", SHA256: strings.Repeat("c", 64)},
			"runner_config":         {Path: "calls/001/inputs/runner_config", SHA256: strings.Repeat("d", 64)},
		},
	}
	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	writeReceipt := func(payload []byte, signature []byte) string {
		t.Helper()
		encoded, err := json.Marshal(executionReceipt{
			PayloadBase64:   base64.StdEncoding.EncodeToString(payload),
			SignatureBase64: base64.StdEncoding.EncodeToString(signature),
		})
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, encoded, 0600); err != nil {
			t.Fatal(err)
		}
		hash := sha256.Sum256(payload)
		return hex.EncodeToString(hash[:])
	}
	digest := writeReceipt(payload, ed25519.Sign(private, payload))
	if actual, err := verifyReceiptFile(path, key, digest); err != nil || actual != digest {
		t.Fatalf("valid online receipt rejected: %v", err)
	}
	binary := filepath.Join(t.TempDir(), "receipt-verifier")
	if output, err := exec.Command("go", "build", "-o", binary, "main.go", "witness_service.go").CombinedOutput(); err != nil {
		t.Fatalf("cannot build receipt verifier CLI: %v: %s", err, output)
	}
	output, err := exec.Command(binary, "--receipt", path, "--public-key", key, "--expected-receipt-payload-sha256", digest).CombinedOutput()
	if err != nil || !bytes.Contains(output, []byte(`"phase":"receipt"`)) || !bytes.Contains(output, []byte(`"verified":true`)) {
		t.Fatalf("valid receipt CLI rejected: %v: %s", err, output)
	}
	if _, err := verifyReceiptFile(path, key, strings.Repeat("f", 64)); err == nil {
		t.Fatal("receipt with wrong expected payload hash accepted")
	}
	if _, err := verifyReceiptFile(path, base64.StdEncoding.EncodeToString(otherPublic), digest); err == nil {
		t.Fatal("receipt with wrong public key accepted")
	}
	writeReceipt(payload, ed25519.Sign(private, []byte("different")))
	if _, err := verifyReceiptFile(path, key, digest); err == nil {
		t.Fatal("receipt with wrong signature accepted")
	}
	badEvent := []byte(`{"not":"an execution event"}`)
	badDigest := writeReceipt(badEvent, ed25519.Sign(private, badEvent))
	if _, err := verifyReceiptFile(path, key, badDigest); err == nil {
		t.Fatal("signed non-event accepted")
	}
	delete(event.Artifacts, "runner_config")
	missingRole, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	missingDigest := writeReceipt(missingRole, ed25519.Sign(private, missingRole))
	if _, err := verifyReceiptFile(path, key, missingDigest); err == nil {
		t.Fatal("signed event missing an input artifact role accepted")
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("another-file", path); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyReceiptFile(path, key, digest); err == nil {
		t.Fatal("symlinked receipt accepted")
	}
}
