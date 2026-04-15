#!/usr/bin/env bash
# setup.sh - Complete setup for ChatDev MAST benchmark reproduction
#
# This script:
# 1. Clones ChatDev (if not already cloned)
# 2. Creates a Python virtual environment and installs dependencies
# 3. Generates MAST-hardened YAML workflow from baseline
# 4. Verifies all files are in place
#
# Usage: ./setup.sh
# 
# After setup, run benchmarks with:
#   ./run_baseline.sh --subset 10   # Baseline on 10 HumanEval problems
#   ./run_mast.sh --subset 10       # MAST-hardened on 10 HumanEval problems
#   python compare_results.py       # Compare results
#
# Environment variables needed for benchmark runs:
#   OPENAI_API_KEY  - Your OpenAI API key
#   OPENAI_BASE_URL - Optional. Custom API base URL

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATDEV_ROOT="$(dirname "$SCRIPT_DIR")"
SETUP_ROOT="$(dirname "$CHATDEV_ROOT")"

echo "=========================================="
echo " ChatDev MAST Benchmark Setup"
echo "=========================================="
echo ""

# Step 1: Check/Clone ChatDev
echo "[1/5] Checking ChatDev repository..."
if [ -d "$CHATDEV_ROOT" ] && [ -d "$CHATDEV_ROOT/.git" ]; then
    echo "  ChatDev already cloned at: $CHATDEV_ROOT"
else
    echo "  Cloning ChatDev..."
    git clone https://github.com/OpenBMB/ChatDev.git "$CHATDEV_ROOT"
    echo "  Cloned successfully."
fi
echo ""

# Step 2: Create venv and install dependencies
echo "[2/5] Setting up Python environment..."
VENV_DIR="$CHATDEV_ROOT/venv"
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists at: $VENV_DIR"
else
    echo "  Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "  Installing ChatDev dependencies..."
pip install -r "$CHATDEV_ROOT/requirements.txt" --no-deps -q 2>/dev/null || \
    pip install -r "$CHATDEV_ROOT/requirements.txt" -q 2>/dev/null || \
    echo "  WARNING: Some dependencies may have failed. Core packages likely installed."

echo "  Installing additional packages..."
pip install human-eval openpyxl anthropic -q 2>/dev/null
echo "  Dependencies installed."
echo ""

# Step 3: Generate MAST-hardened YAML
echo "[3/5] Generating MAST-hardened workflow YAML..."
if [ -f "$SCRIPT_DIR/ChatDev_v1_mast.yaml" ]; then
    echo "  MAST YAML already exists. Regenerating..."
fi
python3 "$SCRIPT_DIR/generate_mast_yaml.py"
echo ""

# Step 4: Verify file structure
echo "[4/5] Verifying file structure..."
ERRORS=0

check_file() {
    if [ -f "$1" ]; then
        echo "  [OK] $1"
    else
        echo "  [MISSING] $1"
        ERRORS=$((ERRORS + 1))
    fi
}

check_file "$CHATDEV_ROOT/yaml_instance/ChatDev_v1.yaml"
check_file "$SCRIPT_DIR/ChatDev_v1_mast.yaml"
check_file "$SCRIPT_DIR/generate_mast_yaml.py"
check_file "$SCRIPT_DIR/run_baseline.sh"
check_file "$SCRIPT_DIR/run_mast.sh"
check_file "$SCRIPT_DIR/compare_results.py"
check_file "$SCRIPT_DIR/ceo_prompt.txt"
check_file "$SCRIPT_DIR/programmer_prompt.txt"
check_file "$SCRIPT_DIR/code_reviewer_prompt.txt"
check_file "$SCRIPT_DIR/test_engineer_prompt.txt"
check_file "$SCRIPT_DIR/cpo_prompt.txt"

echo ""

# Step 5: Verify MAST markers in YAML
echo "[5/5] Verifying MAST hardening markers..."
MAST_COUNT=$(grep -c "MAST HARDENING" "$SCRIPT_DIR/ChatDev_v1_mast.yaml" 2>/dev/null || echo "0")
echo "  MAST HARDENING markers found: $MAST_COUNT (expected: 9)"
if [ "$MAST_COUNT" -ge 9 ]; then
    echo "  [OK] All roles have MAST hardening"
else
    echo "  [WARNING] Expected 9 MAST markers, found $MAST_COUNT"
    echo "  Re-run: python3 $SCRIPT_DIR/generate_mast_yaml.py"
fi

echo ""
echo "=========================================="
echo " Setup Complete!"
echo "=========================================="
echo ""
echo "File inventory:"
echo "  Baseline YAML:   $CHATDEV_ROOT/yaml_instance/ChatDev_v1.yaml"
echo "  MAST YAML:       $SCRIPT_DIR/ChatDev_v1_mast.yaml"
echo "  Baseline runner:  $SCRIPT_DIR/run_baseline.sh"
echo "  MAST runner:      $SCRIPT_DIR/run_mast.sh"
echo "  Compare script:   $SCRIPT_DIR/compare_results.py"
echo ""
echo "MAST-hardened prompt files:"
echo "  CEO:              $SCRIPT_DIR/ceo_prompt.txt"
echo "  Programmer:       $SCRIPT_DIR/programmer_prompt.txt"
echo "  Code Reviewer:    $SCRIPT_DIR/code_reviewer_prompt.txt"
echo "  Test Engineer:    $SCRIPT_DIR/test_engineer_prompt.txt"
echo "  CPO:              $SCRIPT_DIR/cpo_prompt.txt"
echo ""
echo "To run benchmarks:"
echo "  export OPENAI_API_KEY=your-key"
echo "  cd $CHATDEV_ROOT"
echo "  source venv/bin/activate"
echo "  ./mast_hardened/run_baseline.sh --subset 10"
echo "  ./mast_hardened/run_mast.sh --subset 10"
echo "  python mast_hardened/compare_results.py"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo "WARNING: $ERRORS files missing. Review above."
    exit 1
fi