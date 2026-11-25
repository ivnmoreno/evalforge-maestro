#!/usr/bin/env bash
set -euo pipefail

FORMAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SORRY_PROBE="$TMP_DIR/probe_sorry.lean"
cat > "$SORRY_PROBE" <<'EOF'
import EvalForgeAudit

theorem probe_sorry_should_fail : True := by
  sorry

audit_allowed_axioms probe_sorry_should_fail
EOF

AXIOM_PROBE="$TMP_DIR/probe_custom_axiom.lean"
cat > "$AXIOM_PROBE" <<'EOF'
import EvalForgeAudit

axiom customBadAxiom : True

theorem probe_custom_axiom_should_fail : True :=
  customBadAxiom

audit_allowed_axioms probe_custom_axiom_should_fail
EOF

echo "Running negative probe 1: verifying sorryAx rejection..."
set +e
SORRY_OUTPUT="$(cd "$FORMAL_DIR" && lake env lean "$SORRY_PROBE" 2>&1)"
SORRY_RC=$?
set -e
if [ "$SORRY_RC" -eq 0 ]; then
  echo "ERROR: sorry probe unexpectedly succeeded!" >&2
  exit 1
fi
if ! printf '%s\n' "$SORRY_OUTPUT" | grep -q "sorryAx"; then
  echo "ERROR: sorry probe failed without naming sorryAx:" >&2
  printf '%s\n' "$SORRY_OUTPUT" >&2
  exit 1
fi
echo "PASS: sorry probe rejected (exit=$SORRY_RC, detected sorryAx)."

echo "Running negative probe 2: verifying custom axiom rejection..."
set +e
AXIOM_OUTPUT="$(cd "$FORMAL_DIR" && lake env lean "$AXIOM_PROBE" 2>&1)"
AXIOM_RC=$?
set -e
if [ "$AXIOM_RC" -eq 0 ]; then
  echo "ERROR: custom axiom probe unexpectedly succeeded!" >&2
  exit 1
fi
if ! printf '%s\n' "$AXIOM_OUTPUT" | grep -q "customBadAxiom"; then
  echo "ERROR: custom axiom probe failed without naming customBadAxiom:" >&2
  printf '%s\n' "$AXIOM_OUTPUT" >&2
  exit 1
fi
echo "PASS: custom axiom probe rejected (exit=$AXIOM_RC, detected customBadAxiom)."

echo "All Lean negative fault-detection probes passed."
