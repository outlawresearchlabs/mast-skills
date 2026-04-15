#!/usr/bin/env python3
"""Download and inspect the MAST HuggingFace dataset."""

from huggingface_hub import hf_hub_download
import json
from collections import Counter

REPO_ID = "mcemri/MAD"

# Download human-labeled dataset (ground truth)
print("Downloading human-labeled dataset...")
file_path = hf_hub_download(repo_id=REPO_ID, filename="MAD_human_labelled_dataset.json", repo_type="dataset")
with open(file_path, "r") as f:
    human_data = json.load(f)
print(f"Human-labeled: {len(human_data)} records")

# Inspect structure
if human_data:
    sample = human_data[0]
    print(f"\nFirst record keys: {list(sample.keys())}")
    for k, v in sample.items():
        if isinstance(v, str) and len(v) > 200:
            print(f"  {k}: (string, {len(v)} chars)")
        elif isinstance(v, (dict, list)):
            print(f"  {k}: ({type(v).__name__}, len={len(v)})")
        else:
            print(f"  {k}: {repr(v)}")

    # Check if failure_modes has the right structure
    if "failure_modes" in sample:
        fm = sample["failure_modes"]
        print(f"\nFailure modes type: {type(fm)}")
        if isinstance(fm, dict):
            print(f"Failure mode keys: {list(fm.keys())}")

# Count failure modes in human dataset
mode_counts = Counter()
for d in human_data:
    if "failure_modes" in d:
        fm = d["failure_modes"]
        if isinstance(fm, dict):
            for k, v in fm.items():
                if v:
                    mode_counts[k] += 1

print(f"\nHuman-labeled failure mode distribution:")
for k in sorted(mode_counts.keys()):
    print(f"  {k}: {mode_counts[k]} traces")

# Download full dataset
print(f"\nDownloading full dataset...")
file_path2 = hf_hub_download(repo_id=REPO_ID, filename="MAD_full_dataset.json", repo_type="dataset")
with open(file_path2, "r") as f:
    full_data = json.load(f)
print(f"Full dataset: {len(full_data)} records")

# Count failure modes in full dataset
mode_counts_full = Counter()
for d in full_data:
    if "failure_modes" in d:
        fm = d["failure_modes"]
        if isinstance(fm, dict):
            for k, v in fm.items():
                if v:
                    mode_counts_full[k] += 1

print(f"\nFull dataset failure mode distribution:")
for k in sorted(mode_counts_full.keys()):
    print(f"  {k}: {mode_counts_full[k]} traces")

# Save file paths for later use
print(f"\nFile paths:")
print(f"  Human: {file_path}")
print(f"  Full: {file_path2}")