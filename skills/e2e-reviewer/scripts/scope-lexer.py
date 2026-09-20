# SPDX-License-Identifier: Apache-2.0
"""Bounded literal translation of the two scope-source.sh AWK machines.

Fallback is mandatory for unproved transport/encoding cases. This is not a JS
parser and deliberately preserves the shell lexers' different semantics.
"""
import re

SPACE = ' \t\r\v\f\n'
WS = r'[ \t\r\v\f\n]'
SENTINEL = '__E2E_UNREPRESENTABLE__'
DIRECT = re.compile(r'(import|export)[^;]*from'+WS+r'*[\'"`]@playwright/test[\'"`]|require'+WS+r'*\('+WS+r'*[\'"`]@playwright/test[\'"`]'+WS+r'*\)|import'+WS+r'*\('+WS+r'*[\'"`]@playwright/test[\'"`]'+WS+r'*\)')
RELATIVE = re.compile(r'(?:(?:import|export)[^;]*?from'+WS+r'*|require'+WS+r'*\('+WS+r'*|import'+WS+r'*\('+WS+r'*|import'+WS+r'+)__E2E_STR__\.\.?/.*?__E2E_END__')
REGEX_CONTEXT = re.compile(r'(^|[^A-Za-z0-9_$])(return|throw|case|yield)'+WS+r'*$|=>'+WS+r'*$|(^|[^A-Za-z0-9_$])(if|while|for|with)'+WS+r'*\([^)]*\)'+WS+r'*$')
JSX_TEXT_BEFORE = re.compile(r'<([A-Za-z][A-Za-z0-9:._-]*)(?:'+WS+r'[^<>]*)?>[^<{]*$')

class Fallback(Exception): pass

def escape(s, i):
    c = s[i+1:i+2]
    if not c: return '', 1
    def point(digits):
        value = int(digits,16)
        return chr(value) if 32 <= value <= 126 else SENTINEL
    if c == 'u':
        if s[i+2:i+3] == '{':
            end = s.find('}',i+3)
            digits = s[i+3:end] if end >= 0 else ''
            if digits and re.fullmatch('[0-9A-Fa-f]+',digits): return point(digits), end-i+1
        else:
            digits = s[i+2:i+6]
            if re.fullmatch('[0-9A-Fa-f]{4}',digits): return point(digits),6
        return 'u',2
    if c == 'x':
        digits = s[i+2:i+4]
        if re.fullmatch('[0-9A-Fa-f]{2}',digits): return point(digits),4
        return 'x',2
    return (SENTINEL if c in '01234567ntrbfv' else c),2

def quote_is_jsx_text(line, i):
    # Keep this deliberately narrower than a JSX parser. Both tags must be on
    # this line, which avoids letting a TypeScript angle-bracket assertion
    # turn the rest of the file into JSX text.
    opening = JSX_TEXT_BEFORE.search(line[:i])
    if opening is None: return False
    prefix = line[:opening.start()].rstrip()
    words = prefix.split()
    plausible = prefix[-1:] in '=(:,[{>?' or prefix.endswith('=>') or words[-1:] == ['return']
    if prefix and not plausible: return False
    closing = re.match(r'^[^<{]*</([A-Za-z][A-Za-z0-9:._-]*)'+WS+r'*>', line[i+1:])
    return closing is not None and opening.group(1) == closing.group(1)

def executable(source, relative=False, retained='@playwright/test'):
    # latin1 indexing is byte indexing; callers conservatively accept ASCII.
    text = source.decode('latin1')
    block = regex = escaped = regex_class = False
    quote = value = previous = ''
    depth = 0
    result = []
    lines = text.split('\n')
    if lines[-1] == '': lines.pop()  # awk has no extra record for trailing LF.
    for line in lines:
        out = []
        emit = len(line) <= 65536
        i = 0
        while i < len(line):
            c = line[i]; n = line[i+1:i+2]; i += 1
            if block:
                if c == '*' and n == '/': block = False; i += 1
                continue
            if not relative and regex:
                if escaped: escaped = False
                elif c == '\\': escaped = True
                elif c == '[': regex_class = True
                elif c == ']': regex_class = False
                elif c == '/' and not regex_class:
                    regex = False; out.append('__REGEX__'); previous = '/'
                continue
            if quote:
                if relative:
                    if escaped: value += c; escaped = False
                    elif c == '\\': value += c; escaped = True
                    elif c == quote: out.extend(('__E2E_STR__',value,'__E2E_END__')); quote = value = ''
                    else: value += c
                elif c == '\\':
                    decoded, span = escape(line,i-1); value += decoded; i += span-1
                elif quote == '`' and c == '$' and n == '{':
                    quote = value = ''; depth = 1; i += 1
                elif c == quote:
                    if retained and value == retained: out.extend((quote,value,quote))
                    quote = value = ''
                else: value += c
                continue
            if not relative and depth and c == '{':
                depth += 1
                if emit: out.append(c)
                continue
            if not relative and depth and c == '}':
                depth -= 1
                if depth == 0: quote = '`'; value = ''
                elif emit: out.append(c)
                continue
            if c in '\'"' and quote_is_jsx_text(line, i-1):
                if emit: out.append(c)
                previous = c
                continue
            if c in '\'"`': quote = c; value = ''; continue
            if c == '/' and n == '*': block = True; i += 1; continue
            if c == '/' and n == '/': break
            if not relative and c == '/' and (not previous or previous in '=(:,!{[;?&|' or REGEX_CONTEXT.search(''.join(out))):
                regex = True; regex_class = False; continue
            if emit: out.append(c)
            if not relative and c not in SPACE: previous = c
        result.append(''.join(out)+'\n')
    return ''.join(result)

def metadata(source, *, allow_positive_for_differential=False):
    # Binary rg policy and locale/Unicode character classes are not proven.
    if b'\0' in source or any(c >= 128 for c in source): raise Fallback('binary/non-ASCII source')
    # Oversized/large output can expose awk/tr/rg -q SIGPIPE under pipefail.
    # Preserve the shell transport verdict instead of changing it to a pure
    # regular-expression Boolean. Typical small backend files use this path.
    if len(source) > 32768: raise Fallback('large source transport semantics')
    # Python's backtracking matcher can revisit many overlapping import
    # prefixes. Retain the bounded shell backend for token-dense inputs.
    if sum(source.count(word) for word in (b'import', b'export', b'require')) > 64:
        raise Fallback('dense module tokens require original helper')
    if source.count(b'/') > 64:
        raise Fallback('dense slash tokens require original helper')
    direct = executable(source).replace('\n',' ')
    if sum(direct.count(word) for word in ('import', 'export', 'require')) > 64:
        raise Fallback('dense executable module tokens require original helper')
    found = DIRECT.search(direct) is not None
    if found and not allow_positive_for_differential:
        raise Fallback('positive early-exit pipe transport requires original helper')
    refs = executable(source, relative=True).replace('\n',' ')
    if sum(refs.count(word) for word in ('import', 'export', 'require')) > 64:
        raise Fallback('dense relative module tokens require original helper')
    imports = []
    for match in RELATIVE.finditer(refs):
        # sed uses greedy leading .*; embedded sentinel words are significant.
        value = re.sub(r'^.*__E2E_STR__(.*)__E2E_END__.*$',r'\1',match.group())
        imports.append(value)
    return found, imports
