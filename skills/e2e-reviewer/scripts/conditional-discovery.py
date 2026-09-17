#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Conservative #5a file preselection; never replaces the final classifier."""
import argparse
import hashlib
import os
import re
import stat
import sys

FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
MAX_SOURCE = 4 * 1024 * 1024
# Non-ASCII leading bytes conservatively include every Unicode whitespace.
# The ASCII word boundary may overselect if followed by a Unicode letter.
RAW_IF = re.compile(rb'^[ \t\r\v\f\x80-\xff]*if\b')
ALIAS = re.compile(rb'import[^\n]*expect[^\n]*as')
TOKEN = re.compile(rb'expect|assert|should')
SPECIAL = re.compile(rb'[\x22\x27`/]')
QUOTE_SPECIAL = re.compile(rb'[\x22\x27`\\]')
AWK_BLANK = b' \t\r\x0b\x0c'
REGEX_OPENERS = b'=(:,!{[;?&|'
TAIL_KEEP = b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$=> \t\r\x0b\x0c'
TAIL_FOLD = bytes(value if value in TAIL_KEEP else 35 for value in range(256))
REGEX_KEYWORD = re.compile(rb'(?:^|[^A-Za-z0-9_$])(?:return|throw|case|yield)[ \t\r\x0b\x0c]*$')
REGEX_ARROW = re.compile(rb'=>[ \t\r\x0b\x0c]*$')
IDENTITY = re.compile(rb'(?:-?[0-9]+:){6}[0-9a-f]{64}')


def records(path):
    """Read strict NUL records, retaining arbitrary filesystem path bytes."""
    with open(path, 'rb') as stream:
        pending = b''
        while True:
            chunk = stream.read(65536)
            if not chunk:
                if pending:
                    raise ValueError('unterminated NUL record')
                return
            parts = (pending + chunk).split(b'\0')
            pending = parts.pop()
            if len(pending) > 1024 * 1024:
                raise ValueError('oversized NUL record')
            for part in parts:
                if not part:
                    raise ValueError('empty NUL record')
                yield part


def read_manifest(path):
    entries = iter(records(path))
    result = {}
    for name in entries:
        identity = next(entries, None)
        if identity is None or not IDENTITY.fullmatch(identity) or name in result:
            raise ValueError('malformed or duplicate candidate manifest')
        result[name] = identity
    return result


def executable_lines(source):
    """Byte port of conditional_assertion_hit_matches' AWK lexical state.

    Output suppression on long rows still advances quote/comment state. Lexing
    before each target only changes output, so one forward pass is sufficient.
    Regex literals follow the AWK rule: a slash starts one unless the last
    significant byte implies division, or the ASCII-folded tail ends in a
    return/throw/case/yield keyword or ``=>``. Its body is dropped, and an
    unterminated literal ends at the row boundary.
    """
    block = False
    quote = None
    escaped = False
    division = False
    tail = b''
    for line in source.split(b'\n'):
        output = []
        emit = len(line) <= 65536
        regex = False
        regex_class = False
        regex_escaped = False
        i = 0
        while i < len(line):
            if block:
                end = line.find(b'*/', i)
                if end < 0:
                    break
                block = False
                i = end + 2
            elif regex:
                char = line[i]
                if regex_escaped:
                    regex_escaped = False
                elif char == 92:
                    regex_escaped = True
                elif char == 91:
                    regex_class = True
                elif char == 93:
                    regex_class = False
                elif char == 47 and not regex_class:
                    regex = False
                    division = True
                    tail += b'/'
                i += 1
            elif quote is not None:
                if escaped:
                    escaped = False
                    i += 1
                    continue
                match = QUOTE_SPECIAL.search(line, i)
                if match is None:
                    break
                i = match.start()
                char = line[i]
                if char == 92:
                    escaped = True
                elif char == quote:
                    if emit:
                        output.append(b'__STR__')
                    quote = None
                i += 1
            else:
                match = SPECIAL.search(line, i)
                end = match.start() if match else len(line)
                segment = line[i:end]
                if emit:
                    output.append(segment)
                significant = segment.rstrip(AWK_BLANK)
                if significant:
                    division = significant[-1] not in REGEX_OPENERS
                tail = (tail + segment.translate(TAIL_FOLD))[-16:]
                i = end
                if i == len(line):
                    break
                char = line[i]
                pair = line[i:i + 2]
                if (char == 47 and pair not in (b'//', b'/*') and
                        (not division or REGEX_KEYWORD.search(tail) or REGEX_ARROW.search(tail))):
                    regex = True
                    regex_class = False
                    regex_escaped = False
                    i += 1
                    continue
                division = char not in REGEX_OPENERS
                tail = (tail + line[i:i + 1].translate(TAIL_FOLD))[-16:]
                if char in (34, 39, 96):
                    quote = char
                    i += 1
                elif pair == b'/*':
                    block = True
                    i += 2
                elif pair == b'//':
                    break
                else:
                    if emit:
                        output.append(b'/')
                    i += 1
        yield b''.join(output)


def retain(source):
    if b'\0' in source or ALIAS.search(source):
        return True
    if not source.isascii():
        try:
            source.decode('utf-8')
        except UnicodeDecodeError:
            return True
        # UTF-8 never hides ASCII syntax in a multibyte character. AWK may
        # count bytes or characters depending on locale, however, so retain
        # the entire file if its long-row output policy might differ.
        if any(len(line) > 65536 for line in source.split(b'\n')):
            return True
    latest_if = -41
    for number, (raw, code) in enumerate(zip(source.split(b'\n'), executable_lines(source))):
        if RAW_IF.search(raw):
            latest_if = number
        if number - latest_if <= 40 and TOKEN.search(code):
            return True
    return False


def inspect_source(path, expected):
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('candidate is not a regular file')
        digest = hashlib.sha256()
        source = bytearray()
        oversized = False
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            if not oversized:
                if len(source) + len(chunk) > MAX_SOURCE:
                    oversized = True
                    source.clear()
                else:
                    source.extend(chunk)
        after = os.fstat(fd)
        current = os.lstat(path)
        if any(getattr(before, field) != getattr(after, field) or
               getattr(after, field) != getattr(current, field) for field in FIELDS):
            raise ValueError('candidate changed while reading')
        actual = (':'.join(str(getattr(after, field)) for field in FIELDS) + ':' + digest.hexdigest()).encode('ascii')
        if actual != expected:
            raise ValueError('candidate manifest mismatch')
        return oversized or retain(bytes(source))
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        manifest = read_manifest(args.manifest)
        seen = set()
        with open(args.output, 'wb') as output:
            for path in records(args.paths):
                if path in seen or path not in manifest:
                    raise ValueError('duplicate or unknown candidate path')
                seen.add(path)
                output.write(b'1\0' if inspect_source(path, manifest[path]) else b'0\0')
    except (OSError, ValueError) as error:
        print('error: conditional discovery: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
