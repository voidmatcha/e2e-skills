// SPDX-License-Identifier: Apache-2.0
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func witnessFixture(t *testing.T) (*witnessService, string, string) {
	t.Helper()
	bundle, attestation, publicKey, privateKey, claim := fixture(t)
	canonicalBundle, err := filepath.EvalSymlinks(bundle)
	if err != nil {
		t.Fatal(err)
	}
	bundle = canonicalBundle
	if err := os.Chown(bundle, -1, os.Getegid()); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(bundle, 0750); err != nil {
		t.Fatal(err)
	}
	attestation = filepath.Join(bundle, filepath.Base(attestation))
	signFixture(t, attestation, privateKey, claim)
	operator := filepath.Join(t.TempDir(), "operator")
	if err := os.Mkdir(operator, 0700); err != nil {
		t.Fatal(err)
	}
	operator, err = filepath.EvalSymlinks(operator)
	if err != nil {
		t.Fatal(err)
	}
	keyPath := filepath.Join(operator, "private.key")
	if err := os.WriteFile(keyPath, privateKey, 0600); err != nil {
		t.Fatal(err)
	}
	journal := filepath.Join(operator, "witness.jsonl")
	// Core schedule tests run in one process. Production calls newWitnessService,
	// which separately rejects a same-UID runner before opening these resources.
	service, err := openWitnessService(bundle, attestation, protocolDigest(claim), publicKey, keyPath, journal, os.Geteuid(), os.Getegid())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.close)
	return service, bundle, journal
}

func witnessEvent(t *testing.T, service *witnessService, bundle string, stage string) []byte {
	t.Helper()
	roles := inputRoles
	if stage == "end" {
		roles = outputRoles
	}
	key := service.order[service.index/2]
	references := make(map[string]artifact)
	for _, role := range roles {
		path := filepath.ToSlash(filepath.Join("calls", "0000", map[bool]string{true: "inputs", false: "outputs"}[stage == "begin"], role))
		absolute := filepath.Join(bundle, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(absolute), 0700); err != nil {
			t.Fatal(err)
		}
		for _, directory := range []string{
			filepath.Join(bundle, "calls"),
			filepath.Join(bundle, "calls", "0000"),
			filepath.Join(bundle, "calls", "0000", map[bool]string{true: "inputs", false: "outputs"}[stage == "begin"]),
		} {
			if err := os.Chown(directory, -1, service.artifactGID); err != nil {
				t.Fatal(err)
			}
			if err := os.Chmod(directory, 0750); err != nil {
				t.Fatal(err)
			}
		}
		contents := []byte(stage + ":" + role)
		if err := os.WriteFile(absolute, contents, 0640); err != nil {
			t.Fatal(err)
		}
		if err := os.Chown(absolute, -1, service.artifactGID); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(absolute, 0640); err != nil {
			t.Fatal(err)
		}
		hash := sha256.Sum256(contents)
		references[role] = artifact{Path: path, SHA256: hex.EncodeToString(hash[:])}
	}
	raw, err := json.Marshal(executionEvent{
		SchemaVersion: 1, ProtocolID: "reviewer-release-v1", CorpusID: service.corpusID,
		EventIndex: service.index, PreviousSHA256: service.previous, Stage: stage,
		CaseID: key.CaseID, Arm: key.Arm, Repetition: key.Repetition, Artifacts: references,
	})
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestWitnessServiceSignsOnlyFrozenOnlineSequence(t *testing.T) {
	service, bundle, journal := witnessFixture(t)
	begin := witnessEvent(t, service, bundle, "begin")
	client, server := net.Pipe()
	defer client.Close()
	done := make(chan error, 1)
	go func() { done <- service.handleConnection(server) }()
	if err := binary.Write(client, binary.BigEndian, uint32(len(begin))); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Write(begin); err != nil {
		t.Fatal(err)
	}
	var length uint32
	if err := binary.Read(client, binary.BigEndian, &length); err != nil {
		t.Fatal(err)
	}
	receipt := make([]byte, length)
	if _, err := io.ReadFull(client, receipt); err != nil {
		t.Fatal(err)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	var signed executionReceipt
	if err := strictJSON(receipt, &signed); err != nil {
		t.Fatal(err)
	}
	signedPayload, err := base64.StdEncoding.Strict().DecodeString(signed.PayloadBase64)
	if err != nil || !bytes.Equal(signedPayload, begin) {
		t.Fatal("signed payload differs from exact request bytes")
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(signed.SignatureBase64)
	if err != nil || !ed25519.Verify(service.privateKey.Public().(ed25519.PublicKey), begin, signature) {
		t.Fatal("witness signature is invalid")
	}
	if content, err := os.ReadFile(journal); err != nil || !bytes.Equal(content, append(receipt, '\n')) {
		t.Fatal("durable journal differs from acknowledged receipt")
	}
	if _, err := service.signEvent(begin); err == nil || !service.failed {
		t.Fatal("duplicate begin was accepted or did not poison the session")
	}
}

func TestWitnessServiceRefusesTamperAndThenNoRetry(t *testing.T) {
	service, bundle, journal := witnessFixture(t)
	begin := witnessEvent(t, service, bundle, "begin")
	var event executionEvent
	if err := json.Unmarshal(begin, &event); err != nil {
		t.Fatal(err)
	}
	bad := event
	bad.Artifacts = make(map[string]artifact, len(event.Artifacts))
	for role, ref := range event.Artifacts {
		bad.Artifacts[role] = ref
	}
	ref := bad.Artifacts["prompt"]
	ref.SHA256 = strings.Repeat("0", 64)
	bad.Artifacts["prompt"] = ref
	badRaw, _ := json.Marshal(bad)
	if _, err := service.signEvent(badRaw); err == nil || service.index != 0 {
		t.Fatal("witness signed changed input bytes")
	}
	if content, err := os.ReadFile(journal); err != nil || len(content) != 0 {
		t.Fatal("refused event reached the durable journal")
	}
	if _, err := service.signEvent(begin); err == nil || service.index != 0 {
		t.Fatal("rejected begin was retried")
	}
}

func TestWitnessServiceChainsBeginAndEnd(t *testing.T) {
	service, bundle, journal := witnessFixture(t)
	begin := witnessEvent(t, service, bundle, "begin")
	if _, err := service.signEvent(begin); err != nil || service.index != 1 {
		t.Fatalf("valid begin was rejected: %v", err)
	}
	beginHash := sha256.Sum256(begin)
	if service.previous != hex.EncodeToString(beginHash[:]) {
		t.Fatal("begin did not advance the predecessor hash")
	}
	end := witnessEvent(t, service, bundle, "end")
	if _, err := service.signEvent(end); err != nil || service.index != 2 {
		t.Fatalf("valid end was rejected: %v", err)
	}
	endHash := sha256.Sum256(end)
	if service.previous != hex.EncodeToString(endHash[:]) {
		t.Fatal("end did not advance the predecessor hash")
	}
	content, err := os.ReadFile(journal)
	if err != nil || len(bytes.Split(bytes.TrimSuffix(content, []byte("\n")), []byte("\n"))) != 2 {
		t.Fatal("witness journal does not contain exactly two complete receipts")
	}
}

func TestWitnessServiceRefusesOperatorPathReuse(t *testing.T) {
	service, bundle, journal := witnessFixture(t)
	protocolBytes, err := os.ReadFile(filepath.Join(bundle, "protocol.txt"))
	if err != nil {
		t.Fatal(err)
	}
	protocolHash := sha256.Sum256(protocolBytes)
	publicKey := base64.StdEncoding.EncodeToString(service.privateKey.Public().(ed25519.PublicKey))
	if duplicate, err := openWitnessService(bundle, filepath.Join(bundle, "pre-run-attestation.json"),
		hex.EncodeToString(protocolHash[:]), publicKey, filepath.Join(filepath.Dir(journal), "private.key"), journal, os.Geteuid(), os.Getegid()); err == nil {
		duplicate.close()
		t.Fatal("existing operator journal allowed a second witness session")
	}
	if err := outsideBundle(filepath.Join(bundle, "private.key"), bundle); err == nil {
		t.Fatal("private key inside evidence bundle was accepted")
	}
	if err := outsideBundle(journal, bundle); err != nil {
		t.Fatal(err)
	}
	if service.index != 0 {
		t.Fatal("operator-path checks advanced the witness schedule")
	}
}

func TestWitnessIdentityRequiresDistinctNonRootUsersAndSharedGroup(t *testing.T) {
	runnerUID := os.Geteuid() + 1
	if runnerUID == 0 {
		runnerUID++
	}
	if os.Geteuid() != 0 {
		if err := validateWitnessIdentity(runnerUID, os.Getegid()); err != nil {
			t.Fatalf("valid declared separation was rejected: %v", err)
		}
	}
	for _, identity := range []struct{ uid, gid int }{
		{os.Geteuid(), os.Getegid()},
		{0, os.Getegid()},
		{runnerUID, 1 << 30},
	} {
		if err := validateWitnessIdentity(identity.uid, identity.gid); err == nil {
			t.Fatalf("unsafe witness identity was accepted: %+v", identity)
		}
	}
}

func TestNewWitnessServiceRejectsSameUIDBeforeOpeningOperatorFiles(t *testing.T) {
	journal := filepath.Join(t.TempDir(), "must-not-exist.jsonl")
	_, err := newWitnessService(
		filepath.Join(t.TempDir(), "missing-bundle"), "missing-attestation", strings.Repeat("0", 64),
		"missing-key", filepath.Join(t.TempDir(), "missing-key"), journal, os.Geteuid(), os.Getegid(),
	)
	if err == nil || os.IsExist(err) || !strings.Contains(err.Error(), "distinct") {
		t.Fatalf("production witness factory did not reject same-UID operation first: %v", err)
	}
	if _, statErr := os.Lstat(journal); !os.IsNotExist(statErr) {
		t.Fatalf("same-UID refusal created an operator journal: %v", statErr)
	}
}

func TestWitnessServiceRejectsUnsafeArtifactMetadata(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*witnessService, string) error
	}{
		{"group-writable-file", func(_ *witnessService, bundle string) error {
			return os.Chmod(filepath.Join(bundle, "calls", "0000", "inputs", "prompt"), 0660)
		}},
		{"wrong-runner-uid", func(service *witnessService, _ string) error {
			service.runnerUID++
			return nil
		}},
		{"wrong-artifact-gid", func(service *witnessService, _ string) error {
			service.artifactGID++
			return nil
		}},
		{"world-traversable-directory", func(_ *witnessService, bundle string) error {
			return os.Chmod(filepath.Join(bundle, "calls", "0000", "inputs"), 0755)
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			service, bundle, _ := witnessFixture(t)
			begin := witnessEvent(t, service, bundle, "begin")
			if err := test.mutate(service, bundle); err != nil {
				t.Fatal(err)
			}
			if _, err := service.signEvent(begin); err == nil || !strings.Contains(err.Error(), "ownership or mode differs") {
				t.Fatalf("unsafe artifact metadata was accepted: %v", err)
			}
		})
	}
}

func TestWitnessServiceSocketSupportsSeparateRunnerGroup(t *testing.T) {
	service, _, _ := witnessFixture(t)
	socketBase, err := os.MkdirTemp("/tmp", "rws-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(socketBase) })
	socketBase, err = filepath.EvalSymlinks(socketBase)
	if err != nil {
		t.Fatal(err)
	}
	privateSocketPath := filepath.Join(socketBase, "private.sock")
	if listener, err := service.openSocket(privateSocketPath, os.Getegid()); err == nil {
		listener.Close()
		t.Fatal("owner-only socket directory cannot admit a separate runner user")
	}
	socketDir := filepath.Join(socketBase, "socket")
	if err := os.Mkdir(socketDir, 0710); err != nil {
		t.Fatal(err)
	}
	if err := os.Chown(socketDir, -1, os.Getegid()); err != nil {
		t.Fatal(err)
	}
	socketPath := filepath.Join(socketDir, "witness.sock")
	listener, err := service.openSocket(socketPath, os.Getegid())
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	info, err := os.Lstat(socketPath)
	if err != nil || info.Mode().Perm() != 0660 {
		t.Fatalf("witness socket lacks group-only connection permission: %v", err)
	}
	if _, err := service.openSocket(socketPath, os.Getegid()); err == nil {
		t.Fatal("existing witness socket was reused")
	}
}
