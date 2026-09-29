// SPDX-License-Identifier: Apache-2.0
// Optional operator-side online witness. Its private key and journal must be
// controlled outside the model runner; running this beside the runner is not
// independent evidence.
package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

type witnessService struct {
	root        *os.Root
	bundlePath  string
	privateKey  ed25519.PrivateKey
	journal     *os.File
	order       []callKey
	corpusID    string
	index       int
	previous    string
	failed      bool
	runnerUID   int
	artifactGID int
}

func validateWitnessIdentity(runnerUID, artifactGID int) error {
	if runnerUID < 0 || artifactGID < 0 || runnerUID == 0 || os.Geteuid() == 0 {
		return fmt.Errorf("runner and witness must be distinct non-root identities")
	}
	if runnerUID == os.Geteuid() {
		return fmt.Errorf("runner and witness must use distinct user IDs")
	}
	groups, err := os.Getgroups()
	if err != nil {
		return err
	}
	found := artifactGID == os.Getegid()
	for _, group := range groups {
		found = found || group == artifactGID
	}
	if !found {
		return fmt.Errorf("witness is not a member of the artifact read group")
	}
	return nil
}

func outsideBundle(path, bundle string) error {
	if !filepath.IsAbs(path) || !filepath.IsAbs(bundle) || filepath.Clean(path) != path {
		return fmt.Errorf("operator-owned witness paths must be absolute and canonical")
	}
	resolvedBundle, err := filepath.EvalSymlinks(bundle)
	if err != nil {
		return err
	}
	resolvedParent, err := filepath.EvalSymlinks(filepath.Dir(path))
	if err != nil {
		return err
	}
	relative, err := filepath.Rel(resolvedBundle, resolvedParent)
	if err != nil {
		return err
	}
	if relative == "." || relative != ".." && !strings.HasPrefix(relative, ".."+string(os.PathSeparator)) {
		return fmt.Errorf("operator-owned witness paths must be outside the evidence bundle")
	}
	return nil
}

func privateRegularFile(path string, limit int64) ([]byte, error) {
	if !filepath.IsAbs(path) {
		return nil, fmt.Errorf("operator file must use an absolute path")
	}
	parent := filepath.Dir(path)
	resolvedParent, err := filepath.EvalSymlinks(parent)
	if err != nil || resolvedParent != parent {
		return nil, fmt.Errorf("operator file parent must not contain symlink ancestors")
	}
	info, err := os.Lstat(parent)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("operator file parent must be a private real directory")
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return nil, fmt.Errorf("operator file parent must not be a symlink")
	}
	parentOwner, ok := info.Sys().(*syscall.Stat_t)
	if !ok || int(parentOwner.Uid) != os.Geteuid() {
		return nil, fmt.Errorf("operator file parent must be owned by the witness user")
	}
	root, err := os.OpenRoot(parent)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	file, err := openRegular(root, filepath.Base(path))
	if err != nil {
		return nil, err
	}
	defer file.Close()
	stat, err := file.Stat()
	if err != nil || stat.Size() > limit || stat.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("operator file must be bounded and private")
	}
	fileOwner, ok := stat.Sys().(*syscall.Stat_t)
	if !ok || int(fileOwner.Uid) != os.Geteuid() {
		return nil, fmt.Errorf("operator file must be owned by the witness user")
	}
	return io.ReadAll(io.LimitReader(file, limit+1))
}

func newWitnessService(bundle, attestation, protocolSHA256, publicKeyBase64, privateKeyPath, journalPath string, runnerUID, artifactGID int) (*witnessService, error) {
	if err := validateWitnessIdentity(runnerUID, artifactGID); err != nil {
		return nil, err
	}
	return openWitnessService(bundle, attestation, protocolSHA256, publicKeyBase64, privateKeyPath, journalPath, runnerUID, artifactGID)
}

func openWitnessService(bundle, attestation, protocolSHA256, publicKeyBase64, privateKeyPath, journalPath string, runnerUID, artifactGID int) (*witnessService, error) {
	if !filepath.IsAbs(bundle) || filepath.Clean(bundle) != bundle {
		return nil, fmt.Errorf("witness bundle path must be absolute and canonical")
	}
	resolvedBundle, err := filepath.EvalSymlinks(bundle)
	if err != nil || resolvedBundle != bundle {
		return nil, fmt.Errorf("witness bundle must be a real directory without symlink ancestors")
	}
	bundleInfo, err := os.Lstat(bundle)
	if err != nil || !bundleInfo.IsDir() || bundleInfo.Mode()&os.ModeSymlink != 0 {
		return nil, fmt.Errorf("witness bundle is unavailable")
	}
	bundleOwner, ok := bundleInfo.Sys().(*syscall.Stat_t)
	if !ok || int(bundleOwner.Gid) != artifactGID || bundleInfo.Mode().Perm()&0070 != 0050 || bundleInfo.Mode().Perm()&0027 != 0 {
		return nil, fmt.Errorf("witness bundle must expose read-only traversal through the artifact group")
	}
	claim, _, err := verifyPhase(bundle, attestation, publicKeyBase64, protocolSHA256, "pre_run")
	if err != nil {
		return nil, fmt.Errorf("pre-run attestation: %w", err)
	}
	publicKey, err := base64.StdEncoding.Strict().DecodeString(publicKeyBase64)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("preregistered public key is invalid")
	}
	if err := outsideBundle(privateKeyPath, bundle); err != nil {
		return nil, err
	}
	keyBytes, err := privateRegularFile(privateKeyPath, ed25519.PrivateKeySize)
	if err != nil {
		return nil, fmt.Errorf("operator private key is unavailable: %w", err)
	}
	if len(keyBytes) != ed25519.PrivateKeySize {
		return nil, fmt.Errorf("operator private key has the wrong length")
	}
	privateKey := ed25519.PrivateKey(keyBytes)
	if !privateKey.Public().(ed25519.PublicKey).Equal(ed25519.PublicKey(publicKey)) {
		return nil, fmt.Errorf("operator private key differs from the preregistered public key")
	}
	root, err := os.OpenRoot(bundle)
	if err != nil {
		return nil, err
	}
	caseIDs, err := verifyCorpusCommitment(root, claim.Bindings["corpus_commitment"], claim.CorpusID)
	if err != nil {
		root.Close()
		return nil, fmt.Errorf("signed corpus commitment: %w", err)
	}
	order, err := frozenCallOrder(caseIDs)
	if err != nil {
		root.Close()
		return nil, err
	}
	if !filepath.IsAbs(journalPath) || filepath.Clean(journalPath) != journalPath {
		root.Close()
		return nil, fmt.Errorf("witness journal path must be absolute and canonical")
	}
	if err := outsideBundle(journalPath, bundle); err != nil {
		root.Close()
		return nil, err
	}
	journalParent := filepath.Dir(journalPath)
	resolvedParent, err := filepath.EvalSymlinks(journalParent)
	if err != nil || resolvedParent != journalParent {
		root.Close()
		return nil, fmt.Errorf("witness journal parent must not contain symlink ancestors")
	}
	parentInfo, err := os.Lstat(journalParent)
	if err != nil || !parentInfo.IsDir() || parentInfo.Mode()&os.ModeSymlink != 0 || parentInfo.Mode().Perm()&0077 != 0 {
		root.Close()
		return nil, fmt.Errorf("witness journal parent must be a private real directory")
	}
	journalOwner, ok := parentInfo.Sys().(*syscall.Stat_t)
	if !ok || int(journalOwner.Uid) != os.Geteuid() {
		root.Close()
		return nil, fmt.Errorf("witness journal parent must be owned by the witness user")
	}
	journal, err := os.OpenFile(journalPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		root.Close()
		return nil, fmt.Errorf("witness journal already exists or cannot be reserved: %w", err)
	}
	if err := syncDirectory(journalParent); err != nil {
		journal.Close()
		root.Close()
		return nil, err
	}
	return &witnessService{root: root, bundlePath: bundle, privateKey: privateKey, journal: journal, order: order, corpusID: claim.CorpusID, previous: strings.Repeat("0", 64), runnerUID: runnerUID, artifactGID: artifactGID}, nil
}

func syncDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}

func (service *witnessService) close() {
	service.journal.Close()
	service.root.Close()
}

func (service *witnessService) signEvent(raw []byte) ([]byte, error) {
	if service.failed {
		return nil, fmt.Errorf("witness session already failed; no event may be retried")
	}
	receipt, err := service.signEventOnce(raw)
	if err != nil {
		service.failed = true
	}
	return receipt, err
}

func (service *witnessService) verifyArtifactAccess(path string) error {
	parts := strings.Split(path, "/")
	if len(parts) != 4 || parts[0] != "calls" || parts[1] == "" || parts[2] == "" || parts[3] == "" {
		return fmt.Errorf("execution artifact path is outside the shared witness boundary")
	}
	for index := 1; index <= 3; index++ {
		name := strings.Join(parts[:index], "/")
		info, err := service.root.Lstat(name)
		if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("shared artifact directory is unavailable")
		}
		owner, ok := info.Sys().(*syscall.Stat_t)
		if !ok {
			return fmt.Errorf("shared artifact directory ownership is unavailable")
		}
		if int(owner.Uid) != service.runnerUID || int(owner.Gid) != service.artifactGID || info.Mode().Perm() != 0750 {
			return fmt.Errorf("shared artifact directory ownership or mode differs at %s (uid=%d gid=%d mode=%v)", name, owner.Uid, owner.Gid, info.Mode())
		}
	}
	info, err := service.root.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("shared artifact file is unavailable")
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !ok || int(owner.Uid) != service.runnerUID || int(owner.Gid) != service.artifactGID ||
		info.Mode().Perm() != 0640 || info.Mode()&(os.ModeSetuid|os.ModeSetgid|os.ModeSticky) != 0 {
		return fmt.Errorf("shared artifact file ownership or mode differs")
	}
	return nil
}

func (service *witnessService) signEventOnce(raw []byte) ([]byte, error) {
	if service.index >= 2*len(service.order) {
		return nil, fmt.Errorf("witness schedule is already complete")
	}
	var event executionEvent
	if err := strictJSON(raw, &event); err != nil {
		return nil, fmt.Errorf("invalid execution event: %w", err)
	}
	if err := verifyExecutionEventShape(event); err != nil {
		return nil, err
	}
	key := service.order[service.index/2]
	stage := "begin"
	roles := inputRoles
	if service.index%2 == 1 {
		stage = "end"
		roles = outputRoles
	}
	if event.CorpusID != service.corpusID || event.EventIndex != service.index || event.PreviousSHA256 != service.previous ||
		event.Stage != stage || event.CaseID != key.CaseID || event.Arm != key.Arm || event.Repetition != key.Repetition {
		return nil, fmt.Errorf("execution event differs from signed corpus schedule or predecessor")
	}
	limits := map[string]int64{
		"prompt": 1 << 20, "staged_case_manifest": 4 << 20, "staged_skill_manifest": 4 << 20, "runner_config": 1 << 20,
		"codex_jsonl": 8 << 20, "stderr": 1 << 20, "final_response": 8 << 20, "mcp_journal": 128 << 20, "transcript_report": 1 << 20,
	}
	for _, role := range roles {
		ref := event.Artifacts[role]
		expectedPath := fmt.Sprintf("calls/%04d/%s/%s", service.index/2, map[bool]string{true: "inputs", false: "outputs"}[stage == "begin"], role)
		if ref.Path != expectedPath {
			return nil, fmt.Errorf("execution artifact path differs from the frozen call directory")
		}
		if err := service.verifyArtifactAccess(ref.Path); err != nil {
			return nil, fmt.Errorf("execution artifact %s: %w", role, err)
		}
		bytes, err := readBoundedFile(service.root, ref.Path, limits[role])
		if err != nil {
			return nil, fmt.Errorf("execution artifact %s: %w", role, err)
		}
		hash := sha256.Sum256(bytes)
		if hex.EncodeToString(hash[:]) != ref.SHA256 {
			return nil, fmt.Errorf("execution artifact %s hash differs", role)
		}
	}
	receipt, err := json.Marshal(executionReceipt{
		PayloadBase64:   base64.StdEncoding.EncodeToString(raw),
		SignatureBase64: base64.StdEncoding.EncodeToString(ed25519.Sign(service.privateKey, raw)),
	})
	if err != nil {
		return nil, err
	}
	if _, err := service.journal.Write(append(receipt, '\n')); err != nil {
		return nil, err
	}
	if err := service.journal.Sync(); err != nil {
		return nil, err
	}
	hash := sha256.Sum256(raw)
	service.previous = hex.EncodeToString(hash[:])
	service.index++
	return receipt, nil
}

func (service *witnessService) openSocket(socketPath string, runnerGID int) (net.Listener, error) {
	if !filepath.IsAbs(socketPath) || filepath.Clean(socketPath) != socketPath {
		return nil, fmt.Errorf("witness socket path must be absolute and canonical")
	}
	if err := outsideBundle(socketPath, service.bundlePath); err != nil {
		return nil, err
	}
	if runnerGID < 0 {
		return nil, fmt.Errorf("a dedicated runner-access socket group is required")
	}
	parent := filepath.Dir(socketPath)
	resolvedParent, err := filepath.EvalSymlinks(parent)
	if err != nil || resolvedParent != parent {
		return nil, fmt.Errorf("witness socket parent must not contain symlink ancestors")
	}
	info, err := os.Lstat(parent)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0017 != 0010 || info.Mode().Perm()&0020 != 0 || info.Mode().Perm()&0700 != 0700 {
		return nil, fmt.Errorf("witness socket parent must be a real operator-owned directory with group traversal but no group write or other access")
	}
	owner, ok := info.Sys().(*syscall.Stat_t)
	if !ok || int(owner.Uid) != os.Geteuid() || int(owner.Gid) != runnerGID {
		return nil, fmt.Errorf("witness socket parent owner or group differs from the operator and runner-access group")
	}
	if _, err := os.Lstat(socketPath); err == nil {
		return nil, fmt.Errorf("witness socket path already exists")
	} else if !os.IsNotExist(err) {
		return nil, err
	}
	previousUmask := syscall.Umask(0077)
	listener, err := net.Listen("unix", socketPath)
	syscall.Umask(previousUmask)
	if err != nil {
		return nil, err
	}
	if err := os.Chown(socketPath, -1, runnerGID); err != nil {
		listener.Close()
		return nil, err
	}
	if err := os.Chmod(socketPath, 0660); err != nil {
		listener.Close()
		return nil, err
	}
	if err := syncDirectory(parent); err != nil {
		listener.Close()
		return nil, err
	}
	return listener, nil
}

func (service *witnessService) serve(socketPath string, runnerGID int) error {
	listener, err := service.openSocket(socketPath, runnerGID)
	if err != nil {
		return err
	}
	defer listener.Close()
	for service.index < 2*len(service.order) {
		connection, err := listener.Accept()
		if err != nil {
			return err
		}
		if err := service.handleConnection(connection); err != nil {
			return err // never retry or skip a failed event
		}
	}
	return nil
}

func (service *witnessService) handleConnection(connection net.Conn) (failure error) {
	defer connection.Close()
	defer func() {
		if failure != nil {
			service.failed = true
		}
	}()
	if err := connection.SetDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return err
	}
	var length uint32
	if err := binary.Read(connection, binary.BigEndian, &length); err != nil {
		return err
	}
	if length == 0 || length > 16<<10 {
		return fmt.Errorf("witness event is empty or oversized")
	}
	data := make([]byte, length)
	if _, err := io.ReadFull(connection, data); err != nil {
		return err
	}
	receipt, err := service.signEvent(data)
	if err != nil {
		return err
	}
	if err := binary.Write(connection, binary.BigEndian, uint32(len(receipt))); err != nil {
		return err
	}
	for len(receipt) > 0 {
		written, writeErr := connection.Write(receipt)
		if writeErr != nil {
			return writeErr
		}
		if written == 0 {
			return fmt.Errorf("witness connection accepted no receipt bytes")
		}
		receipt = receipt[written:]
	}
	return nil
}
