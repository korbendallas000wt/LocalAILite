#!/usr/bin/env python3
import argparse
import json
import sys
import os
import torch
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from diffusers import (
    StableDiffusionXLPipeline,
    EulerDiscreteScheduler,
    EulerAncestralDiscreteScheduler,
    DPMSolverMultistepScheduler,
    DDIMScheduler,
    PNDMScheduler
)
from core import checkpoint_manager
from core import history_manager


def get_scheduler(name, config):
    # Маппинг коротких имен и полных имен классов
    scheduler_map = {
        "Euler": EulerDiscreteScheduler,
        "EulerDiscreteScheduler": EulerDiscreteScheduler,
        "Euler A": EulerAncestralDiscreteScheduler,
        "EulerAncestralDiscreteScheduler": EulerAncestralDiscreteScheduler,
        "DPM++ 2M": DPMSolverMultistepScheduler,
        "DPMSolverMultistepScheduler": DPMSolverMultistepScheduler,
        "DDIM": DDIMScheduler,
        "DDIMScheduler": DDIMScheduler,
        "PNDM": PNDMScheduler,
        "PNDMScheduler": PNDMScheduler,
    }
    
    scheduler_class = scheduler_map.get(name, EulerDiscreteScheduler)
    return scheduler_class.from_config(config)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative_prompt", default="")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg", type=float, default=7.0)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--scheduler", default="Euler")
    parser.add_argument("--device", default="cpu")
    
    # Аргументы от DiffusersWorker
    parser.add_argument("--preview-every", type=int, default=0)
    parser.add_argument("--preview-start", type=int, default=1)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--preview-dir", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--cache_dir", default=None)
    parser.add_argument("--no-safety-checker", action="store_true")
    
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint_file", default=None)
    
    args = parser.parse_args()

    print(f"[INFO] Script started. Args: {vars(args)}", flush=True)

    # Создаём выходную папку
    os.makedirs(args.output_dir, exist_ok=True)

    # Загружаем модель
    print(f"[INFO] Loading model: {args.model}", flush=True)
    dtype = torch.float16 if args.device == "cuda" else torch.float32
    
    try:
        if os.path.isfile(args.model) and (args.model.endswith('.safetensors') or args.model.endswith('.ckpt')):
            print(f"[INFO] Single file model detected", flush=True)
            pipe = StableDiffusionXLPipeline.from_single_file(
                args.model,
                torch_dtype=dtype,
                use_safetensors=args.model.endswith('.safetensors')
            )
        else:
            pipe = StableDiffusionXLPipeline.from_pretrained(
                args.model,
                torch_dtype=dtype,
                cache_dir=args.cache_dir if args.cache_dir else None
            )
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}", flush=True)
        sys.exit(1)

    pipe.to(args.device)

    # === Оптимизация CPU для генерации и финального декодирования ===
    if args.device == "cpu":
        cpu_count = os.cpu_count() or 4
        torch.set_num_threads(cpu_count)
        torch.set_num_interop_threads(1)
        print(f"[INFO] CPU threads set to: {cpu_count}", flush=True)
        


    # Настройка scheduler
    pipe.scheduler = get_scheduler(args.scheduler, pipe.scheduler.config)

    # Seed
    generator = torch.Generator(device=args.device)
    actual_seed = args.seed
    if actual_seed < 0:
        actual_seed = torch.randint(0, 2**32, (1,)).item()
    generator.manual_seed(actual_seed)

    # Resume logic
    start_step = 0
    latents = None
    if args.resume and args.checkpoint_file:
        print(f"[INFO] Resuming from checkpoint: {args.checkpoint_file}", flush=True)
        json_data, torch_data = checkpoint_manager.load_archived_checkpoint(args.checkpoint_file)
        if json_data and torch_data:
            start_step = json_data.get("current_step", 0)
            latents = torch_data["latents"].to(args.device)
            generator.set_state(torch_data["generator_state"])
            print(f"[INFO] Resumed at step {start_step}", flush=True)

    # Callback для diffusers 0.39+
    def callback_on_step_end(pipe, step, timestep, callback_kwargs):
        latents = callback_kwargs["latents"]
        step_number = step + 1
        
        # Сохраняем ТОЛЬКО латенты (.pt) и метаданные (.json) для истории
        # Декодирование в PNG здесь НЕ делаем, чтобы не тормозить генерацию!
        
        pt_path = os.path.join(args.history_dir, f"step_{step_number:04d}.pt")
        json_path = os.path.join(args.history_dir, f"step_{step_number:04d}.json")
        
        # 1. Сохраняем PT (быстрая операция, просто дамп тензора)
        torch.save({"latents": latents.cpu()}, pt_path)
        
        # 2. Сохраняем JSON
        meta = {
            "step": step_number, 
            "timestep": int(timestep.item() if hasattr(timestep, 'item') else timestep),
            "seed": actual_seed
        }
        with open(json_path, "w") as f:
            json.dump(meta, f)
            
        # Выводим прогресс для UI (без пути к картинке, так как её ещё нет)
        progress_json = json.dumps({
            "type": "step",
            "step": step_number,
            "total": args.steps,
            "image_path": "" # Пусто, превью пока нет
        })
        print(progress_json, flush=True)
        
        return callback_kwargs


    # Генерация
    print(f"[INFO] Starting generation: {args.steps} steps, seed={actual_seed}", flush=True)
    result = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        num_inference_steps=args.steps,
        guidance_scale=args.cfg,
        width=args.width,
        height=args.height,
        generator=generator,
        latents=latents,
        callback_on_step_end=callback_on_step_end,
        callback_on_step_end_tensor_inputs=["latents"],
        output_type="pil"
    )

    # Финальное сохранение
    final_image = result.images[0]
    final_path = os.path.join(args.output_dir, f"sdxl_{actual_seed}.png")
    final_image.save(final_path)
    
    # Сохраняем метаданные генерации
    metadata = {
        "prompt": args.prompt,
        "negative_prompt": args.negative_prompt,
        "steps": args.steps,
        "cfg": args.cfg,
        "size": f"{args.width}x{args.height}",
        "seed": actual_seed,
        "scheduler": args.scheduler,
        "model": os.path.basename(args.model)
    }
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # === Явная выгрузка модели для быстрого освобождения ресурсов ===
    print("[INFO] Unloading model...", flush=True)
    del pipe
    del result
    if args.device == "cuda":
        torch.cuda.empty_cache()
    import gc
    gc.collect()
    print("[INFO] Model unloaded", flush=True)

    finish_json = json.dumps({
        "type": "done",
        "final_path": final_path,
        "seed": actual_seed
    })
    print(finish_json, flush=True)
    print("[INFO] Generation completed successfully", flush=True)


if __name__ == "__main__":
    main()
