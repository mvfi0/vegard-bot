"""
Validates and converts dataset JSONL files into the format expected by train.py.

Dataset format (each line in your .jsonl files):
{
    "conversations": [
        {"role": "user", "content": "your message"},
        {"role": "assistant", "content": "V.E.G.A.R.D. reply"}
    ]
}

Usage:
    python finetune/prepare_dataset.py --input finetune/dataset/your_data.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


SYSTEM_PROMPT = (
    "You are V.E.G.A.R.D. — Versatile Engine for General Answers, Reasoning & Dialogue. "
    "You are Vegard's personal AI assistant. Be casual, direct, and match his language and slang."
)


def validate_entry(entry: dict, line_num: int) -> bool:
    if "conversations" not in entry:
        print(f"Line {line_num}: missing 'conversations' key")
        return False
    convs = entry["conversations"]
    if not isinstance(convs, list) or len(convs) < 2:
        print(f"Line {line_num}: 'conversations' must have at least 2 messages")
        return False
    for msg in convs:
        if "role" not in msg or "content" not in msg:
            print(f"Line {line_num}: each message needs 'role' and 'content'")
            return False
        if msg["role"] not in ("user", "assistant"):
            print(f"Line {line_num}: role must be 'user' or 'assistant', got '{msg['role']}'")
            return False
    if convs[0]["role"] != "user":
        print(f"Line {line_num}: conversation must start with 'user'")
        return False
    if convs[-1]["role"] != "assistant":
        print(f"Line {line_num}: conversation must end with 'assistant'")
        return False
    return True


def to_chatml(entry: dict) -> str:
    """Convert a conversation entry to ChatML format for training."""
    parts = [f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>"]
    for msg in entry["conversations"]:
        parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    return "\n".join(parts)


def process(input_path: Path, output_path: Path):
    valid, invalid = 0, 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open(encoding="utf-8") as f_in, \
         output_path.open("w", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Line {i}: invalid JSON — {e}")
                invalid += 1
                continue

            if validate_entry(entry, i):
                f_out.write(json.dumps({"text": to_chatml(entry)}, ensure_ascii=False) + "\n")
                valid += 1
            else:
                invalid += 1

    print(f"\nDone. Valid: {valid} | Skipped: {invalid}")
    print(f"Output: {output_path}")
    if valid < 50:
        print(f"Warning: {valid} examples is very low. Aim for 200+ for meaningful results.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to your .jsonl dataset file")
    parser.add_argument("--output", default="finetune/dataset/train_ready.jsonl")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    process(input_path, Path(args.output))
