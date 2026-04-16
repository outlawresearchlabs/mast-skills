#!/usr/bin/env python3
"""
Create a lightweight MAST-hardened ChatDev YAML.
Injects compressed MAST rules (4 bullet points) into each agent role.
Avoids the prompt bloat that can cause context management issues (FM-1.4)
on models with limited context windows.
"""
import os
import re

BASELINE = os.environ.get("CHATDEV_YAML", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ChatDev", "yaml_instance", "ChatDev_v1_gw.yaml"))
OUTPUT = os.path.join(os.path.dirname(BASELINE), "ChatDev_v1_mast_lite.yaml")
MODEL_NAME = "gemma4:31b-cloud"

# Lightweight MAST rules - 4 compressed bullets that cover the key failure modes
# These are ~200 chars vs ~2000 chars for the full protocol block
MAST_LITE = """

MAST Rules (mandatory, override conflicting instructions):
- Anti-loop: Never repeat a completed step. If done, move on.
- Clarify first: If requirements are ambiguous, ask before implementing.
- Verify before save: Check code is complete and correct before writing files.
- Share all info: Never withhold known constraints or limits from other agents.
"""

with open(BASELINE) as f:
    content = f.read()

# Replace gpt-4o with gateway model
content = content.replace("name: gpt-4o", f"name: {MODEL_NAME}")

# Find each agent role block and append MAST_LITE right after the role text
# Pattern: "role: |-\n  <existing text>\n        provider:"
# We insert MAST_LITE before "provider:"

# For each occurrence of "role: |-" followed by content then "provider:"
def inject_mast(match):
    role_content = match.group(1)
    # Strip trailing whitespace from role content
    role_content = role_content.rstrip()
    # Calculate indentation (should be 8 spaces for ChatDev YAML)
    indent = "        "
    # Add MAST rules with proper indentation
    mast_lines = MAST_LITE.strip().split('\n')
    mast_indented = '\n' + indent + ('\n' + indent).join(mast_lines)
    return f"role: |-\n{role_content}{mast_indented}\n{indent}provider:"

content_new = re.sub(
    r'role: \|-\n(.*?)(\n        provider:)',
    inject_mast,
    content,
    flags=re.DOTALL
)

with open(OUTPUT, 'w') as f:
    f.write(content_new)

# Verify
with open(OUTPUT) as f:
    new_content = f.read()

mast_count = new_content.count("MAST Rules")
agent_count = new_content.count(f"name: {MODEL_NAME}")
print(f"MAST rule blocks injected: {mast_count}")
print(f"Model name replacements: {agent_count}")

import os
print(f"Baseline size: {os.path.getsize(BASELINE)} bytes")
print(f"MAST lite size: {os.path.getsize(OUTPUT)} bytes")
print(f"Full MAST size: {os.path.getsize(os.path.join(os.path.dirname(BASELINE), 'ChatDev_v1_mast_gw.yaml'))} bytes")