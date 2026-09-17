# SPDX-License-Identifier: Apache-2.0
# Shared executable-source extraction for scanner scope and runtime checks.

source_has_playwright_module_reference() {
  source_executable_code "$1" @playwright/test |
    tr '\n' ' ' |
    scanner_rg -q "(import|export)[^;]*from[[:space:]]*['\"\`]@playwright/test['\"\`]|require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|import[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)"
}

# Run one source lexer awk program. Callers read empty lexer output as "no
# framework reference", so a failed awk (unreadable file, runtime error, killed
# process) must never pass for a clean negative. A failure is recorded in the
# runtime error file, where abort_on_rg_error and the scope worker already fail
# closed. Output streams exactly as before, and the lexer status is returned
# unchanged, so readable sources keep their pipeline verdicts and a reader that
# stops early (rg -q, head) still ends the lexer early. That closed pipe is not
# a lexer failure: SIGPIPE (141) is never recorded, and when SIGPIPE was
# inherited as ignored, awk reports the same closed pipe as an ordinary write
# error, so a non-signal status is recorded only if the lexer also fails with
# its output discarded.
run_source_lexer() {
  local lexer_rc
  awk "$@" 2>/dev/null
  lexer_rc=$?
  case "$lexer_rc" in
    0|141) return "$lexer_rc" ;;
  esac
  if [[ "$lexer_rc" -gt 128 ]] || ! awk "$@" >/dev/null 2>&1; then
    [[ -n "${RG_RUNTIME_ERROR_FILE:-}" ]] &&
      printf 'awk %s\n' "$lexer_rc" >> "$RG_RUNTIME_ERROR_FILE"
  fi
  return "$lexer_rc"
}

source_executable_code() {
  local f="$1" retained_string="${2:-}"
  run_source_lexer -v retained="$retained_string" '
    # A JavaScript string literal is not its own source text: `\u0040pkg` and
    # `@pkg` are the same module specifier. Decode escapes so an obfuscated
    # import cannot make a real framework reference invisible (or an unrelated
    # package look like one). Sequences whose value cannot occur inside a
    # package specifier (control characters, non-ASCII code points) decode to a
    # sentinel word so they compare unequal to every package name instead of
    # accidentally matching one.
    function js_hex_value(digits,   k, value, digit) {
      value = 0
      for (k = 1; k <= length(digits); k++) {
        digit = index("0123456789abcdef", tolower(substr(digits, k, 1))) - 1
        if (digit < 0) return -1
        value = value * 16 + digit
      }
      return value
    }
    function js_code_point_text(code) {
      if (code >= 32 && code <= 126) return sprintf("%c", code)
      return "__E2E_UNREPRESENTABLE__"
    }
    # Decodes the escape sequence starting at s[i] (which is a backslash) and
    # records how many source characters it spans in js_escape_span so the
    # caller can advance its cursor past the whole sequence.
    function js_escape_text(s, i,   next_char, digits, brace_end) {
      next_char = substr(s, i + 1, 1)
      if (next_char == "") {
        # Trailing backslash: a line continuation contributes no characters.
        js_escape_span = 1
        return ""
      }
      if (next_char == "u") {
        if (substr(s, i + 2, 1) == "{") {
          brace_end = index(substr(s, i + 3), "}")
          if (brace_end > 0) {
            digits = substr(s, i + 3, brace_end - 1)
            if (digits ~ /^[0-9A-Fa-f]+$/) {
              js_escape_span = brace_end + 3
              return js_code_point_text(js_hex_value(digits))
            }
          }
        } else {
          digits = substr(s, i + 2, 4)
          if (digits ~ /^[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]$/) {
            js_escape_span = 6
            return js_code_point_text(js_hex_value(digits))
          }
        }
        js_escape_span = 2
        return "u"
      }
      if (next_char == "x") {
        digits = substr(s, i + 2, 2)
        if (digits ~ /^[0-9A-Fa-f][0-9A-Fa-f]$/) {
          js_escape_span = 4
          return js_code_point_text(js_hex_value(digits))
        }
        js_escape_span = 2
        return "x"
      }
      js_escape_span = 2
      if (next_char ~ /^[0-7]$/) return "__E2E_UNREPRESENTABLE__"
      if (index("ntrbfv", next_char) > 0) return "__E2E_UNREPRESENTABLE__"
      return next_char
    }
    function executable_source(s, want_output,    out, i, c, nchar) {
      out = ""
      # A line this long is generated or vendored, never test source. The
      # embedded Python path already refuses it as an "oversized source line";
      # holding the awk path to the same contract also stops the character loop
      # below from going quadratic on a minified bundle.
      if (length(s) > 65536) want_output = 0
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_regex) {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == "[") {
            regex_class = 1
          } else if (c == "]") {
            regex_class = 0
          } else if (c == "/" && !regex_class) {
            lex_regex = 0
            out = out "__REGEX__"
            prev_sig = "/"
          }
          continue
        }
        if (lex_quote != "") {
          if (c == "\\") {
            lex_value = lex_value js_escape_text(s, i)
            i += js_escape_span - 1
          } else if (lex_quote == "`" && c == "$" && nchar == "{") {
            lex_quote = ""
            template_depth = 1
            lex_value = ""
            i++
          } else if (c == lex_quote) {
            if (retained != "" && lex_value == retained)
              out = out lex_quote lex_value lex_quote
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (template_depth > 0 && c == "{") {
          template_depth++
          if (want_output) out = out c
          continue
        }
        if (template_depth > 0 && c == "}") {
          template_depth--
          if (template_depth == 0) {
            lex_quote = "`"
            lex_value = ""
          } else {
            if (want_output) out = out c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        if (c == "/" && (prev_sig == "" ||
            prev_sig ~ /[=(:,!{\[;?&|]/ ||
            out ~ /(^|[^A-Za-z0-9_$])(return|throw|case|yield)[[:space:]]*$/ ||
            out ~ /=>[[:space:]]*$/ ||
            out ~ /(^|[^A-Za-z0-9_$])(if|while|for|with)[[:space:]]*\([^)]*\)[[:space:]]*$/)) {
          lex_regex = 1
          regex_class = 0
          continue
        }
        if (want_output) out = out c
        if (c !~ /[[:space:]]/) prev_sig = c
      }
      return out
    }
    { print executable_source($0, 1) }
  ' "$f"
}

source_relative_module_references() {
  run_source_lexer '
    function executable_source(s, want_output,    out, i, c, nchar) {
      out = ""
      # A line this long is generated or vendored, never test source. The
      # embedded Python path already refuses it as an "oversized source line";
      # holding the awk path to the same contract also stops the character loop
      # below from going quadratic on a minified bundle.
      if (length(s) > 65536) want_output = 0
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        if (want_output) out = out c
      }
      return out
    }
    { print executable_source($0, 1) }
  ' "$1" |
    tr '\n' ' ' |
    scanner_rg -o "(?:(?:import|export)[^;]*?from[[:space:]]*|require[[:space:]]*\\([[:space:]]*|import[[:space:]]*\\([[:space:]]*|import[[:space:]]+)__E2E_STR__\\.\\.?/.*?__E2E_END__" 2>/dev/null |
    sed -E 's/^.*__E2E_STR__(.*)__E2E_END__.*$/\1/'
}

# Return through the caller's local SOURCE_PATH_DIRNAME. Keep platform dirname
# behavior for unusual separators and command-substitution newline handling.
source_path_dirname() {
  local path="$1" parent="${1%/*}"
  if [[ "$path" == */* && "$path" != */ && "$path" != //* && "$path" != -* &&
        "$path" != *$'\n'* && "$parent" != */ ]]; then
    SOURCE_PATH_DIRNAME="${parent:-/}"
  else
    SOURCE_PATH_DIRNAME="$(dirname "$path")"
  fi
}

source_relative_module_candidate_paths() {
  local f="$1" import_path="$2" module_path module_base SOURCE_PATH_DIRNAME
  source_path_dirname "$f"
  module_path="$SOURCE_PATH_DIRNAME/$import_path"
  module_base="$module_path"
  case "$module_path" in
    *.js|*.jsx|*.mjs|*.cjs) module_base="${module_path%.*}" ;;
  esac
  printf '%s\n' \
    "$module_path" \
    "$module_base.ts" "$module_base.tsx" "$module_base.js" "$module_base.jsx" \
    "$module_base.mts" "$module_base.mjs" "$module_base.cts" "$module_base.cjs" \
    "$module_path/index.ts" "$module_path/index.tsx" \
    "$module_path/index.js" "$module_path/index.jsx" \
    "$module_path/index.mts" "$module_path/index.mjs" \
    "$module_path/index.cts" "$module_path/index.cjs"
}

resolve_relative_module_candidates() {
  local f="$1" import_path="$2" candidate candidate_dir candidate_real candidate_base SOURCE_PATH_DIRNAME
  while IFS= read -r candidate; do
    [[ -f "$candidate" && ! -L "$candidate" ]] || continue
    source_path_dirname "$candidate"
    candidate_dir=$(cd "$SOURCE_PATH_DIRNAME" 2>/dev/null && pwd -P) || continue
    if [[ "$candidate" != -* && "$candidate" != */ && "$candidate" != *$'\n'* ]]; then
      candidate_base="${candidate##*/}"
    else
      candidate_base="$(basename "$candidate")"
    fi
    candidate_real="$candidate_dir/$candidate_base"
    case "$candidate_real" in
      "$PROJECT_ROOT_REAL"/*) printf '%s\n' "$candidate_real" ;;
    esac
  done < <(source_relative_module_candidate_paths "$f" "$import_path")
}

# Sourcing defines only functions. Executing opens a private, NUL-framed
# request stream for the Python metadata cache; no eval or shell interpolation.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -uo pipefail
  PATH=/usr/bin:/bin:/usr/sbin:/sbin
  export PATH
  PROJECT_ROOT_REAL="$1"
  RG_BIN="$2"
  RG_RUNTIME_ERROR_FILE="$3"
  scanner_rg() {
    "$RG_BIN" "$@"
    local rc=$?
    if [[ "$rc" -gt 1 ]]; then
      printf '%s\n' "$rc" > "$RG_RUNTIME_ERROR_FILE"
    fi
    return "$rc"
  }
  while IFS= read -r -d '' operation &&
        IFS= read -r -d '' source_file &&
        IFS= read -r -d '' import_path; do
    case "$operation" in
      direct)
        if source_has_playwright_module_reference "$source_file"; then
          printf '1\0'
        else
          printf '0\0'
        fi
        ;;
      imports)
        while IFS= read -r value; do printf '%s\0' "$value"; done \
          < <(source_relative_module_references "$source_file")
        ;;
      candidates)
        while IFS= read -r value; do printf '%s\0' "$value"; done \
          < <(source_relative_module_candidate_paths "$source_file" "$import_path")
        ;;
      resolve)
        while IFS= read -r value; do printf '%s\0' "$value"; done \
          < <(resolve_relative_module_candidates "$source_file" "$import_path")
        ;;
      *) exit 2 ;;
    esac
    printf '\0'
  done
fi
