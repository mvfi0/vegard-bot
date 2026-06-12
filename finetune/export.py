"""
Merges the LoRA adapter into the base model and exports to GGUF for Ollama.

Requirements:
  - llama.cpp must be cloned and built (see instructions below)
  - pip install -r finetune/requirements.txt

llama.cpp setup (run once):
    git clone https://github.com/ggerganov/llama.cpp
    cd llama.cpp
    cmake -B build -DGGML_CUDA=ON
    cmake --build build --config Release -j

Usage:
    python finetune/export.py
    python finetune/export.py --adapter finetune/output/adapter --llamacpp path/to/llama.cpp
"""

import argparse
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
ADAPTER_DIR = "finetune/output/adapter"
MERGED_DIR = "finetune/output/merged"
GGUF_PATH = "finetune/output/vegard.gguf"
LLAMA_CPP_DIR = "llama.cpp"


def merge(adapter_dir: str, merged_dir: str):
    print("Loading base model (full precision for merging)...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="cpu",
    )
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir)

    print("Merging LoRA adapter...")
    model = PeftModel.from_pretrained(model, adapter_dir)
    model = model.merge_and_unload()

    print(f"Saving merged model to {merged_dir}...")
    Path(merged_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)
    print("Merge complete.")


def convert_to_gguf(merged_dir: str, gguf_path: str, llamacpp_dir: str):
    convert_script = Path(llamacpp_dir) / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        print(f"llama.cpp not found at {llamacpp_dir}")
        print("Clone it with: git clone https://github.com/ggerganov/llama.cpp")
        sys.exit(1)

    print(f"Converting to GGUF: {gguf_path}...")
    subprocess.run([
        sys.executable, str(convert_script),
        merged_dir,
        "--outfile", gguf_path,
        "--outtype", "q4_k_m",   # 4-bit quantization, good quality/size tradeoff
    ], check=True)
    print(f"GGUF saved: {gguf_path}")


def create_modelfile(gguf_path: str):
    modelfile_path = Path("finetune/output/Modelfile")
    modelfile_path.write_text(
        f'FROM {Path(gguf_path).resolve()}\n'
        f'PARAMETER temperature 0.8\n'
        f'PARAMETER top_p 0.9\n',
        encoding="utf-8"
    )
    print(f"\nModelfile created: {modelfile_path}")
    print("\nTo load into Ollama:")
    print(f"  ollama create vegard -f {modelfile_path}")
    print(f"  ollama run vegard")
    print("\nThen update OLLAMA_MODEL=vegard in your .env and restart the core.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=ADAPTER_DIR)
    parser.add_argument("--merged", default=MERGED_DIR)
    parser.add_argument("--gguf", default=GGUF_PATH)
    parser.add_argument("--llamacpp", default=LLAMA_CPP_DIR)
    args = parser.parse_args()

    if not Path(args.adapter).exists():
        raise FileNotFoundError(f"Adapter not found: {args.adapter}. Run train.py first.")

    merge(args.adapter, args.merged)
    convert_to_gguf(args.merged, args.gguf, args.llamacpp)
    create_modelfile(args.gguf)
