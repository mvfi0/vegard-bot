"""
QLoRA fine-tuning script for V.E.G.A.R.D.
Fine-tunes LLaMA 3.1 8B Instruct on your custom dataset using 4-bit quantization.

Prerequisites:
  1. pip install -r finetune/requirements.txt
  2. huggingface-cli login  (needs HuggingFace account + Llama 3.1 access approved)
  3. python finetune/prepare_dataset.py --input finetune/dataset/your_data.jsonl

Usage:
    python finetune/train.py
    python finetune/train.py --dataset finetune/dataset/train_ready.jsonl --epochs 3
"""

import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

BASE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
OUTPUT_DIR = "finetune/output/adapter"


def main(dataset_path: str, epochs: int, output_dir: str):
    print(f"Loading dataset from {dataset_path}...")
    dataset = load_dataset("json", data_files=dataset_path, split="train")
    print(f"  {len(dataset)} examples loaded")

    print("Loading base model with 4-bit quantization...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        attn_implementation="eager",
    )
    model.config.use_cache = False

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    print("Applying LoRA adapters...")
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,       # effective batch size = 8
        gradient_checkpointing=True,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        dataset_text_field="text",
        max_seq_length=2048,
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        processing_class=tokenizer,
    )

    print(f"\nStarting training for {epochs} epoch(s)...")
    trainer.train()

    print(f"\nSaving adapter to {output_dir}...")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("Done. Run export.py next to convert for Ollama.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="finetune/dataset/train_ready.jsonl")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--output", default=OUTPUT_DIR)
    args = parser.parse_args()

    if not Path(args.dataset).exists():
        raise FileNotFoundError(
            f"Dataset not found: {args.dataset}\n"
            "Run prepare_dataset.py first."
        )

    main(args.dataset, args.epochs, args.output)
