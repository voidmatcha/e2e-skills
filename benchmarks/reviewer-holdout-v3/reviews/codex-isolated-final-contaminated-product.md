# Isolated final-candidate product review — contaminated snapshot

Date: 2026-07-30  
Decision: **NO-GO for blind sign-off; conditional product pass**  
Score: **84/100**

The reviewer used a temporary-home, no-Git snapshot and did not inspect parent
directories, external skills, user configuration, or logs. The intended blind
boundary nevertheless failed because the snapshot still contained the root
`benchmarks/` directory. The reviewer did not enumerate that directory, but
public documentation and CI evidence validators exposed prior benchmark
information. The score is therefore retained as development feedback, not a
clean blind result.

| Category | Score |
|---|---:|
| Behavior correctness | 23/25 |
| Scanner precision and recall robustness | 17/20 |
| Benchmark validity and unbiasedness | 16/20 |
| Executable evidence | 11/15 |
| Documentation and product clarity | 9/10 |
| Maintainability and security | 8/10 |
| **Total** | **84/100** |

## Ranked findings

1. The review snapshot incorrectly retained `benchmarks/`.
2. The security gate omitted common source/config extensions and converted
   search errors into a clean result.
3. Core CI evidence validators depend on archived files intentionally excluded
   from a truly blind source snapshot.
4. The scanner's unsupported-filename preflight traversed excluded trees,
   making a colon/newline filename in dependencies an operational blocker.
5. The CI ast-grep install used a floating compatible-version range.
6. The opening network statement in `SECURITY.md` was more absolute than the
   generator and debugger workflows support.

The benchmark-dependent validation gaps were caused by the intended blind
exclusions and were not treated as proof that the underlying committed
evidence is invalid. A new snapshot must physically omit all of `benchmarks/`.
