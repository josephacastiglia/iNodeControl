# Preserved project work — 19 October 2026

This is a preservation branch, **not a tested release or an integration merge**.
It records 458 selected files from `iMouseXP-2.0` at base
`01fb669a79e95700a086440b3e2905b0b511cdcb`. The original checkout, index and branch remain unchanged.

The current integrated source is on `local/combined-candidate-20261012`.
Read its `MARKETING-FARM-STATUS.md` and `RESUME-NEXT.md` before development.
Do not reapply this entire snapshot over that candidate: it includes historical,
experimental and negative-control source versions.

Source, scripts, handoffs and safe text evidence are retained byte-for-byte.
The file manifest is `analysis/cross-agent-preservation-20261019/iMouseXP-2.0-files.json`.
Phone captures, SQLite/session stores, binaries, build trees, toolchain caches
and unrelated nested websites remain local. Their omission is deliberate.
The unredacted `backup/*` branch must never be pushed.

The original Gemini installer `tools/setup_imouse_farm.py`, if present here, is
an obsolete preservation artifact: running it can overwrite the hardened source.
Its claims and historical handoff claims are not current acceptance results.
The dedicated Orca/Gemini export has its account header redacted; the exact
original stays in the private local evidence archive.

No deployment, promotion, phone input, release edit or main-branch merge is made
by preserving this work. Use Git with `core.autocrlf=false` when verifying the
manifest against a new checkout, or hash the stored blobs directly.
