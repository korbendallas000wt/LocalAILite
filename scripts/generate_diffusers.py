#!/usr/bin/env python3
import argparse
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import torch
import numpy as np
from PIL import Image
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

def emit(msg):
    """Выводит JSON-сообщение в stdout + plain text для лога"""
    print(json.dumps(msg, ensure_ascii=False), flush=True)
    msg_type = msg.get("type")
    if msg_type == "step":
        step = msg.get("step", 0)
        total = msg.get("total_steps", 0)
        print(f"[STEP] {step}/{total}", flush=True)
    elif msg_type == "status":
        message = msg.get("message", "")
        print(f"[STATUS] {message}", flush=True)
    elif msg_type == "done":
        final_path = msg.get("final_path", "")
        print(f"[DONE] {final_path}", flush=True)
    elif msg_type == "error":
        message = msg.get("message", "")
        print(f"[ERROR] {message}", flush=True)
    elif msg_type == "warning":
        message = msg.get("message", "")
        print(f"[WARNING] {message}", flush=True)

def main():
    last_preview_path = ""
    history_dir = None
    parser = argparse.ArgumentParser(description="SDXL Image Generator")
    parser.add_argument("--prompt", required=True, help="Positive prompt")
    parser.add_argument("--negative", default="", help="Negative prompt")
    parser.add_argument("--model", required=True, help="Model name or path")
    parser.add_argument("--scheduler", default="EulerDiscreteScheduler")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg", type=float, default=7.5)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    parser.add_argument("--preview-every", type=int, default=0,
                        help="Сохранять превью каждые N шагов (0 = выключено)")
    parser.add_argument("--preview-start", type=int, default=1,
                        help="Начинать сохранение превью с этого шага")
    parser.add_argument("--no-safety-checker", action="store_true", help="Disable NSFW filter")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument("--preview-dir", default=None,
                        help="Папка для превью (технические файлы)")
    parser.add_argument("--cache_dir", default=None, help="Cache directory for models")
    parser.add_argument("--history-dir", default=None,
                        help="Папка для сохранения истории генерации (PNG на каждом шаге)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--checkpoint-file", default=None,
                        help="Имя файла архивного чекпоинта (для resume из архива)")
    args = parser.parse_args()
    print(f"[INFO] Script started. Args: {vars(args)}", flush=True)

    # === Режим Resume ===
    if args.resume:
        print(f"[INFO] Resume mode enabled", flush=True)
        if args.checkpoint_file:
            print(f"[INFO] Loading archived checkpoint: {args.checkpoint_file}", flush=True)
            emit({"type": "status", "message": f"Загрузка архивного чекпоинта: {args.checkpoint_file}..."})
            json_data, torch_data = checkpoint_manager.load_archived_checkpoint(args.checkpoint_file)
        else:
            print(f"[INFO] Loading active checkpoint", flush=True)
            if not checkpoint_manager.checkpoint_exists():
                emit({"type": "error", "message": "Чекпоинт не найден"})
                sys.exit(1)
            emit({"type": "status", "message": "Загрузка чекпоинта..."})
            json_data, torch_data = checkpoint_manager.load_checkpoint()
        if not json_data or not torch_data:
            emit({"type": "error", "message": "Не удалось загрузить чекпоинт"})
            sys.exit(1)
        print(f"[INFO] Checkpoint loaded successfully", flush=True)
        args.prompt = json_data["prompt"]
        args.negative = json_data.get("negative_prompt", "")
        args.model = json_data["model"]
        args.scheduler = json_data["scheduler"]
        args.steps = json_data["total_steps"]
        args.cfg = json_data["cfg"]
        args.width = json_data["width"]
        args.height = json_data["height"]
        args.seed = json_data["seed"]
        args.device = json_data["device"]
        args.preview_every = json_data.get("preview_every", 0)
        args.preview_start = json_data.get("preview_start", 1)
        current_step = json_data["current_step"]
        resume_start_step = current_step
        last_preview_path = json_data.get("last_preview_path", "")
        remaining_timesteps_list = json_data["remaining_timesteps"]
        latents = torch_data["latents"].to(args.device)
        scheduler_state = torch_data["scheduler_state"]
        generator_state = torch_data["generator_state"]
        remaining_timesteps = torch.tensor(
            remaining_timesteps_list,
            device=args.device
        )
        emit({"type": "status", "message": f"Продолжение с шага {current_step}/{args.steps}..."})
    else:
        current_step = 0
        resume_start_step = 0
        remaining_timesteps = None
        latents = None
        scheduler_state = None
        generator_state = None

    # Генерация seed
    if args.seed == -1:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()
    else:
        seed = args.seed
    generator = torch.Generator(device=args.device).manual_seed(seed)
    if args.resume and generator_state is not None:
        generator.set_state(generator_state)

    # Загрузка модели
    try:
        emit({"type": "status", "message": "Загрузка модели..."})
        print(f"[INFO] Loading model: {args.model}", flush=True)
        dtype = torch.float16 if args.device == "cuda" else torch.float32
        if os.path.isfile(args.model) and (args.model.endswith('.safetensors') or args.model.endswith('.ckpt')):
            emit({"type": "status", "message": "Загрузка одиночного файла модели..."})
            print(f"[INFO] Single file model detected", flush=True)
            pipe = StableDiffusionXLPipeline.from_single_file(
                args.model,
                torch_dtype=dtype,
                use_safetensors=args.model.endswith('.safetensors')
            )
        else:
            print(f"[INFO] HF model or folder: {args.model}", flush=True)
            pipe = StableDiffusionXLPipeline.from_pretrained(
                args.model,
                torch_dtype=dtype,
                cache_dir=args.cache_dir,
                use_safetensors=True
            )
        print(f"[INFO] Moving model to device: {args.device}", flush=True)
        pipe.to(args.device)
        if args.no_safety_checker:
            try:
                pipe.safety_checker = None
                emit({"type": "status", "message": "Safety Checker отключён"})
                print(f"[INFO] Safety Checker disabled", flush=True)
            except AttributeError:
                pass
        scheduler_map = {
            "EulerDiscreteScheduler": EulerDiscreteScheduler,
            "EulerAncestralDiscreteScheduler": EulerAncestralDiscreteScheduler,
            "DPMSolverMultistepScheduler": DPMSolverMultistepScheduler,
            "DDIMScheduler": DDIMScheduler,
            "PNDMScheduler": PNDMScheduler
        }
        if args.scheduler in scheduler_map:
            pipe.scheduler = scheduler_map[args.scheduler].from_config(pipe.scheduler.config)
            print(f"[INFO] Scheduler set to: {args.scheduler}", flush=True)
        if args.resume and scheduler_state is not None:
            pipe.scheduler.__dict__.update(scheduler_state)
            print(f"[INFO] Scheduler state restored", flush=True)
    except Exception as e:
        print(f"[ERROR] Model loading failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        emit({"type": "error", "message": f"Ошибка загрузки модели: {str(e)}"})
        sys.exit(1)

    # Создаём папку истории (если указана)
    if args.history_dir:
        history_dir = args.history_dir
        os.makedirs(history_dir, exist_ok=True)
        emit({"type": "status", "message": f"История сохраняется в: {history_dir}"})

    # Callback для прогресса и сохранения истории (API diffusers 0.39+)
    def callback_fn(pipe, step_index, timestep, callback_kwargs):
        nonlocal current_step, last_preview_path
        latents = callback_kwargs.get("latents")
        current_step = resume_start_step + step_index + 1
        print(f"[STEP] {current_step}/{args.steps}", flush=True)
        msg = {
            "type": "step",
            "step": current_step,
            "total_steps": args.steps,
            "image_path": ""
        }

        # === Сохраняем чекпоинт синхронно (быстро, ~0.1-0.5 сек на фоне 500 сек шага) ===
        if history_dir and current_step < args.steps:
            try:
                params = {
                    "prompt": args.prompt,
                    "negative_prompt": args.negative,
                    "model": args.model,
                    "scheduler": args.scheduler,
                    "seed": args.seed,
                    "total_steps": args.steps,
                    "width": args.width,
                    "height": args.height,
                    "cfg": args.cfg,
                    "device": args.device
                }
                # Сохраняем PT
                step_pt_path = os.path.join(history_dir, f"step_{current_step:04d}.pt")
                torch.save({
                    "latents": latents.cpu(),
                    "generator_state": generator.get_state(),
                    "params": params,
                    "current_step": current_step,
                    "actual_seed": seed
                }, step_pt_path)
                # Сохраняем JSON
                step_json_data = dict(params)
                step_json_data["current_step"] = current_step
                step_json_path = os.path.join(history_dir, f"step_{current_step:04d}.json")
                with open(step_json_path, "w", encoding="utf-8") as f:
                    json.dump(step_json_data, f, indent=2, ensure_ascii=False)
                print(f"[CHECKPOINT] Saved step {current_step}", flush=True)
            except Exception as e:
                emit({"type": "warning", "message": f"Не удалось сохранить чекпоинт шага {current_step}: {e}"})

        emit(msg)
        return callback_kwargs

    # Генерация
    try:
        emit({"type": "status", "message": "Генерация..."})
        print(f"[INFO] Starting generation: {args.width}x{args.height}, seed={args.seed}, steps={args.steps}", flush=True)
        if args.resume:
            remaining_steps = len(remaining_timesteps)
            if remaining_steps <= 0:
                emit({"type": "error", "message": "Генерация уже завершена в чекпоинте"})
                sys.exit(1)
            print(f"[INFO] Resume: {remaining_steps} remaining steps, timesteps device={remaining_timesteps.device}", flush=True)
            image = pipe(
                prompt=args.prompt,
                negative_prompt=args.negative if args.negative else None,
                width=args.width,
                height=args.height,
                num_inference_steps=remaining_steps,
                guidance_scale=args.cfg,
                generator=generator,
                latents=latents,
                timesteps=remaining_timesteps,
                callback_on_step_end=callback_fn,
                callback_on_step_end_tensor_inputs=["latents"]
            ).images[0]
        else:
            image = pipe(
                prompt=args.prompt,
                negative_prompt=args.negative if args.negative else None,
                width=args.width,
                height=args.height,
                num_inference_steps=args.steps,
                guidance_scale=args.cfg,
                generator=generator,
                callback_on_step_end=callback_fn,
                callback_on_step_end_tensor_inputs=["latents"]
            ).images[0]
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        emit({"type": "error", "message": f"Ошибка генерации: {str(e)}"})
        sys.exit(1)

    # Сохраняем metadata.json в историю
    if history_dir:
        try:
            metadata = {
                "timestamp": os.path.basename(history_dir),
                "prompt": args.prompt,
                "negative_prompt": args.negative,
                "model": args.model,
                "scheduler": args.scheduler,
                "seed": seed,
                "total_steps": args.steps,
                "width": args.width,
                "height": args.height,
                "cfg": args.cfg,
                "device": args.device
            }
            history_manager.save_metadata(history_dir, metadata)
            emit({"type": "status", "message": f"История сохранена: {history_dir}"})
        except Exception as e:
            emit({"type": "warning", "message": f"Не удалось сохранить metadata: {e}"})

    # Сохранение финальной картинки
    try:
        os.makedirs(args.output_dir, exist_ok=True)
        filename = f"sdxl_{seed}.png"
        output_path = os.path.join(args.output_dir, filename)
        image.save(output_path)
        emit({
            "type": "done",
            "final_path": output_path,
            "seed": args.seed
        })
        print(f"[INFO] Generation completed successfully", flush=True)
    except Exception as e:
        print(f"[ERROR] Save failed: {e}", flush=True)
        emit({"type": "error", "message": f"Ошибка сохранения: {str(e)}"})
        sys.exit(1)

if __name__ == "__main__":
    main()
