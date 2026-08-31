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
    parser.add_argument("--resume-history-dir", default=None)
    parser.add_argument("--resume-step-file", default=None)
    parser.add_argument("--resume-start-step", type=int, default=0)
    
    args = parser.parse_args()

    print(f"[INFO] Script started. Args: {vars(args)}", flush=True)

    # Создаём выходную папку
    os.makedirs(args.output_dir, exist_ok=True)

    # === Детекция варианта весов (например, *.fp16.safetensors) ===
    def _detect_variant(model_path):
        """Определяет вариант весов модели по фактическим файлам в папке.

        Возвращает строку вида 'fp16', если веса лежат как *.fp16.safetensors
        и нет обычных *.safetensors, иначе None.
        """
        for subfolder in ('unet', 'vae', 'text_encoder', 'text_encoder_2'):
            subdir = os.path.join(model_path, subfolder)
            if not os.path.isdir(subdir):
                continue
            has_fp16 = False
            has_plain = False
            for f in os.listdir(subdir):
                if f.endswith('.fp16.safetensors'):
                    has_fp16 = True
                elif f.endswith('.safetensors'):
                    has_plain = True
            if has_fp16 and not has_plain:
                return 'fp16'
        return None

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
            variant = _detect_variant(args.model)
            if variant:
                print(f"[INFO] Detected model variant: {variant}", flush=True)
            pipe = StableDiffusionXLPipeline.from_pretrained(
                args.model,
                torch_dtype=dtype,
                variant=variant,
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
    resume_timesteps = None  # Оставшиеся timestep'ы из чекпоинта

    if args.resume and args.resume_history_dir and args.resume_step_file:
        print(f"[INFO] Resuming from history: {args.resume_history_dir}/{args.resume_step_file}", flush=True)
        checkpoint_data = checkpoint_manager.load_step_full(args.resume_history_dir, args.resume_step_file)
        if checkpoint_data is not None:
            latents = checkpoint_data["latents"].to(args.device)
            start_step = args.resume_start_step
            
            # Восстанавливаем scheduler state
            if "scheduler_state" in checkpoint_data:
                pipe.scheduler.__dict__.update(checkpoint_data["scheduler_state"])
                resume_timesteps = pipe.scheduler.timesteps[start_step:]
                print(f"[INFO] Scheduler state restored, timesteps: {len(resume_timesteps)}", flush=True)
            
            # Восстанавливаем generator state
            if "generator_state" in checkpoint_data:
                generator.set_state(checkpoint_data["generator_state"])
                print(f"[INFO] Generator state restored", flush=True)
            
            print(f"[INFO] Resumed at step {start_step}", flush=True)
        else:
            print(f"[ERROR] Failed to load checkpoint from {args.resume_step_file}", flush=True)

    # Callback для diffusers 0.39+
    def callback_on_step_end(pipe, step, timestep, callback_kwargs):
        latents = callback_kwargs["latents"]
        step_number = step + 1 + start_step
        
        # Сохраняем ТОЛЬКО латенты (.pt) и метаданные (.json) для истории
        # Декодирование в PNG здесь НЕ делаем, чтобы не тормозить генерацию!
        
        pt_path = os.path.join(args.history_dir, f"step_{step_number:04d}.pt")
        json_path = os.path.join(args.history_dir, f"step_{step_number:04d}.json")
        
        # 1. Сохраняем PT (латенты + scheduler state + generator state)
        torch.save({
            "latents": latents.cpu(),
            "scheduler_state": {k: v for k, v in pipe.scheduler.__dict__.items()
                               if not callable(v)},
            "generator_state": generator.get_state()
        }, pt_path)
        
        # 2. Сохраняем JSON со ВСЕМИ параметрами генерации
        meta = {
            "step": step_number, 
            "timestep": int(timestep.item() if hasattr(timestep, 'item') else timestep),
            "seed": actual_seed,
            "prompt": args.prompt,
            "negative_prompt": args.negative_prompt,
            "model": os.path.basename(args.model),
            "scheduler": args.scheduler,
            "steps": args.steps,
            "cfg": args.cfg,
            "size": f"{args.width}x{args.height}",
            "width": args.width,
            "height": args.height
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            
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
    # Проверяем, поддерживает ли scheduler custom timesteps
    # Стохастические scheduler'ы (EulerAncestral, LMS) НЕ поддерживают
    scheduler_name = pipe.scheduler.__class__.__name__
    supports_custom_timesteps = scheduler_name not in [
        'EulerAncestralDiscreteScheduler',
        'LMSDiscreteScheduler'
    ]

    if args.resume and resume_timesteps is not None and supports_custom_timesteps:
        # Точный resume: используем оставшиеся timestep'ы из чекпоинта
        print(f"[INFO] Starting generation: {len(resume_timesteps)} remaining steps (resume from {start_step}), seed={actual_seed}", flush=True)
        
        # === ВАЖНО: компенсируем масштабирование латентов в prepare_latents ===
        # Конвейер умножает ВСЕ латенты на init_noise_sigma (строка 726 в pipeline).
        # Для свежей генерации это правильно (масштабирует случайный шум).
        # Для resume — катастрофа (латенты уже на правильном уровне из чекпоинта).
        # Решение: предварительно делим на init_noise_sigma, чтобы конвейерное
        # умножение скомпенсировалось.
        # Нюанс: init_noise_sigma берём для УКОРОЧЕННОГО расписания (resume_timesteps),
        # поэтому сначала настраиваем scheduler на эти timesteps.
        pipe.scheduler.set_timesteps(timesteps=resume_timesteps)
        init_sigma = pipe.scheduler.init_noise_sigma
        latents = latents / init_sigma
        print(f"[INFO] Latents pre-scaled by 1/init_noise_sigma={init_sigma:.4f} to compensate for pipeline scaling", flush=True)
        
        result = pipe(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            timesteps=resume_timesteps,
            guidance_scale=args.cfg,
            width=args.width,
            height=args.height,
            generator=generator,
            latents=latents,
            callback_on_step_end=callback_on_step_end,
            callback_on_step_end_tensor_inputs=["latents"],
            output_type="pil"
        )
    else:
        # Обычная генерация или fallback для стохастических scheduler'ов
        remaining_steps = args.steps - start_step if args.resume and start_step > 0 else args.steps
        print(f"[INFO] Starting generation: {remaining_steps} steps, seed={actual_seed}", flush=True)
        result = pipe(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            num_inference_steps=remaining_steps,
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
    counter = 1
    while os.path.exists(final_path):
        final_path = os.path.join(args.output_dir, f"sdxl_{actual_seed}_{counter}.png")
        counter += 1
    final_image.save(final_path)


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
