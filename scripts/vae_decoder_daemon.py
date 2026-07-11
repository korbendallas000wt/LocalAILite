#!/usr/bin/env python3
"""
VAE Decoder Daemon — отдельный процесс для декодирования latents в PNG.
Мониторит папку history_dir на появление новых .pt файлов,
декодирует их через VAE и сохраняет как step_N.png.

Запускается из DiffusersWorker параллельно с генерацией.
Завершается по SIGTERM или таймауту без новых файлов.

Usage:
    python vae_decoder_daemon.py \
        --history_dir /path/to/history \
        --model /path/to/model \
        --device cuda \
        --cache_dir /path/to/cache \
        --timeout 10
"""
import argparse
import os
import sys
import time
import signal
import json

# Добавляем корень проекта в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
import numpy as np
from PIL import Image
from diffusers import StableDiffusionXLPipeline

# Глобальный флаг для graceful shutdown
_shutdown = False

def signal_handler(signum, frame):
    global _shutdown
    print(f"[VAE_DAEMON] Received signal {signum}, shutting down...", flush=True)
    _shutdown = True

def decode_latents(pipe, latents):
    """Декодирует latents в PIL.Image"""
    with torch.no_grad():
        latents_scaled = latents / pipe.vae.config.scaling_factor
        decoded = pipe.vae.decode(latents_scaled, return_dict=False)[0]
    images = (decoded / 2 + 0.5).clamp(0, 1)
    images = images.cpu().permute(0, 2, 3, 1).numpy()
    image_np = (images[0] * 255).astype(np.uint8)
    return Image.fromarray(image_np)

def load_pt_file(pt_path):
    """Загружает .pt файл и возвращает latents tensor"""
    try:
        # Пробуем прочитать файл несколько раз (на случай, что он ещё пишется)
        for attempt in range(10):
            try:
                data = torch.load(pt_path, map_location="cpu", weights_only=False)
                if isinstance(data, dict) and "latents" in data:
                    return data["latents"]
                elif isinstance(data, torch.Tensor):
                    return data
                else:
                    print(f"[VAE_DAEMON] Unknown format in {pt_path}", flush=True)
                    return None
            except (EOFError, RuntimeError) as e:
                # Файл ещё пишется — ждём
                time.sleep(0.5)
                continue
        print(f"[VAE_DAEMON] Failed to read {pt_path} after 10 attempts", flush=True)
        return None
    except Exception as e:
        print(f"[VAE_DAEMON] Error loading {pt_path}: {e}", flush=True)
        return None

def main():
    global _shutdown

    parser = argparse.ArgumentParser(description="VAE Decoder Daemon")
    parser.add_argument("--history_dir", required=True, help="Папка с .pt файлами")
    parser.add_argument("--model", required=True, help="Путь к модели SDXL")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    parser.add_argument("--cache_dir", default=None, help="Cache directory for HF models")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Секунд без новых файлов до завершения (0 = ждать всегда)")
    parser.add_argument("--single_file", default=None,
                        help="Декодировать только один конкретный файл (например, step_0001.pt)")
    args = parser.parse_args()

    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    print(f"[VAE_DAEMON] Started. history_dir={args.history_dir}", flush=True)
    print(f"[VAE_DAEMON] Model: {args.model}", flush=True)
    print(f"[VAE_DAEMON] Device: {args.device}", flush=True)

    # Загружаем модель
    try:
        print(f"[VAE_DAEMON] Loading model...", flush=True)
        dtype = torch.float16 if args.device == "cuda" else torch.float32
        if os.path.isfile(args.model) and (args.model.endswith('.safetensors') or args.model.endswith('.ckpt')):
            pipe = StableDiffusionXLPipeline.from_single_file(
                args.model,
                torch_dtype=dtype,
                use_safetensors=args.model.endswith('.safetensors')
            )
        else:
            pipe = StableDiffusionXLPipeline.from_pretrained(
                args.model,
                torch_dtype=dtype,
                cache_dir=args.cache_dir,
                use_safetensors=True
            )
        pipe.to(args.device)
        # Оставляем только VAE, выгружаем остальное для экономии памяти
        pipe.unet = None
        pipe.text_encoder = None
        pipe.text_encoder_2 = None
        pipe.tokenizer = None
        pipe.tokenizer_2 = None
        print(f"[VAE_DAEMON] Model loaded, VAE only", flush=True)
    except Exception as e:
        print(f"[VAE_DAEMON] ERROR loading model: {e}", flush=True)
        sys.exit(1)

    # Основной цикл мониторинга
    processed_files = set()
    last_activity = time.time()
    poll_interval = 0.5  # секунд

    print(f"[VAE_DAEMON] Monitoring started (timeout={args.timeout}s)", flush=True)

    while not _shutdown:
        # Сканируем папку
        try:
            files = os.listdir(args.history_dir)
        except Exception as e:
            print(f"[VAE_DAEMON] Error listing directory: {e}", flush=True)
            time.sleep(1)
            continue

        new_pt_files = []
        for f in files:
            if f.endswith('.pt') and f not in processed_files:
                # Если указан single_file — обрабатываем только его
                if args.single_file and f != args.single_file:
                    continue
                pt_path = os.path.join(args.history_dir, f)
                # Проверяем, что файл полностью записан (не растёт)
                try:
                    size1 = os.path.getsize(pt_path)
                    time.sleep(0.2)
                    size2 = os.path.getsize(pt_path)
                    if size1 == size2 and size1 > 0:
                        new_pt_files.append(f)
                except Exception:
                    pass

        if new_pt_files:
            last_activity = time.time()
            for pt_file in sorted(new_pt_files):
                if _shutdown:
                    break
                pt_path = os.path.join(args.history_dir, pt_file)
                print(f"[VAE_DAEMON] Processing: {pt_file}", flush=True)

                # Загружаем latents
                latents = load_pt_file(pt_path)
                if latents is None:
                    continue

                # Переносим на device
                latents = latents.to(args.device)

                # Декодируем
                try:
                    image = decode_latents(pipe, latents)
                    # Сохраняем PNG (меняем расширение .pt на .png)
                    png_file = pt_file.replace('.pt', '.png')
                    png_path = os.path.join(args.history_dir, png_file)
                    image.save(png_path)
                    print(f"[VAE_DAEMON] Saved: {png_file}", flush=True)
                    processed_files.add(pt_file)
                except Exception as e:
                    print(f"[VAE_DAEMON] Error decoding {pt_file}: {e}", flush=True)

        # Проверяем таймаут
        if args.timeout > 0:
            elapsed = time.time() - last_activity
            if elapsed > args.timeout:
                print(f"[VAE_DAEMON] Timeout ({args.timeout}s), shutting down", flush=True)
                break

        time.sleep(poll_interval)

    print(f"[VAE_DAEMON] Shutdown complete. Processed {len(processed_files)} files", flush=True)

if __name__ == "__main__":
    main()
