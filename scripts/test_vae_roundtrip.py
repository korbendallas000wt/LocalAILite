#!/usr/bin/env python3
"""
Тестовый скрипт для проверки VAE encode/decode roundtrip.
Берёт картинку → кодирует в latents → декодирует обратно → сохраняет результат.
Используется для проверки корректности VAE перед img2img интеграцией.

Usage:
    python scripts/test_vae_roundtrip.py \
        --image photo.jpg \
        --model /path/to/sdxl \
        --output_dir data/test_vae/
"""
import argparse
import os
import sys
import torch
import numpy as np
from PIL import Image
from torchvision import transforms

# Добавляем корень проекта в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def encode_image_to_latents(pipe, image_path, device="cuda", dtype=torch.float16):
    """
    Кодирует картинку в латенты через VAE.
    
    Args:
        pipe: StableDiffusionXLPipeline (должен быть загружен)
        image_path: путь к картинке
        device: "cuda" или "cpu"
        dtype: torch.float16 или torch.float32
    
    Returns:
        torch.Tensor: латенты shape [1, 4, H/8, W/8]
    """
    print(f"[INFO] Loading image: {image_path}")
    img = Image.open(image_path).convert("RGB")
    
    # Ресайз до кратного 8 (требование VAE)
    width, height = img.size
    new_width = (width // 8) * 8
    new_height = (height // 8) * 8
    if new_width != width or new_height != height:
        print(f"[INFO] Resizing from {width}×{height} to {new_width}×{new_height} (multiple of 8)")
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Нормализация в [-1, 1]
    transform = transforms.Compose([
        transforms.ToTensor(),  # [0, 1]
        lambda x: x * 2 - 1,    # [-1, 1]
    ])
    image_tensor = transform(img).unsqueeze(0)  # [1, 3, H, W]
    image_tensor = image_tensor.to(device=device, dtype=dtype)
    
    print(f"[INFO] Encoding to latents...")
    # VAE encode
    with torch.no_grad():
        encoded = pipe.vae.encode(image_tensor)
        latents = encoded.latent_dist.sample()
        latents = latents * pipe.vae.config.scaling_factor
    
    print(f"[INFO] Latents shape: {latents.shape}")
    print(f"[INFO] Latents dtype: {latents.dtype}")
    print(f"[INFO] Latents range: [{latents.min().item():.3f}, {latents.max().item():.3f}]")
    
    return latents


def decode_latents_to_image(pipe, latents):
    """
    Декодирует латенты обратно в картинку.
    
    Args:
        pipe: StableDiffusionXLPipeline
        latents: torch.Tensor shape [1, 4, H/8, W/8]
    
    Returns:
        PIL.Image
    """
    print(f"[INFO] Decoding latents to image...")
    with torch.no_grad():
        # Обратное масштабирование
        latents_scaled = latents / pipe.vae.config.scaling_factor
        
        # Декодирование
        decoded = pipe.vae.decode(latents_scaled, return_dict=False)[0]
        
        # Нормализация в [0, 1]
        images = (decoded / 2 + 0.5).clamp(0, 1)
        
        # Конвертация в numpy
        images = images.cpu().permute(0, 2, 3, 1).numpy()
        image_np = (images[0] * 255).round().astype("uint8")
    
    return Image.fromarray(image_np)


def main():
    parser = argparse.ArgumentParser(description="Test VAE encode/decode roundtrip")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument("--model", required=True, help="Model path (SDXL)")
    parser.add_argument("--output_dir", default="data/test_vae", help="Output directory")
    parser.add_argument("--cache_dir", default=None, help="Cache directory for HF models")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu")
    args = parser.parse_args()
    
    print(f"[INFO] Script started. Args: {vars(args)}")
    
    # Создаём выходную папку
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Загружаем модель
    print(f"[INFO] Loading model: {args.model}")
    from diffusers import StableDiffusionXLPipeline
    
    dtype = torch.float16 if args.device == "cuda" else torch.float32
    
    if os.path.isfile(args.model) and (args.model.endswith('.safetensors') or args.model.endswith('.ckpt')):
        print(f"[INFO] Single file model detected")
        pipe = StableDiffusionXLPipeline.from_single_file(
            args.model,
            torch_dtype=dtype,
            use_safetensors=args.model.endswith('.safetensors')
        )
    else:
        print(f"[INFO] HF model or folder: {args.model}")
        pipe = StableDiffusionXLPipeline.from_pretrained(
            args.model,
            torch_dtype=dtype,
            cache_dir=args.cache_dir,
            use_safetensors=True
        )
    
    print(f"[INFO] Moving model to device: {args.device}")
    pipe.to(args.device)
    
    # Кодируем картинку
    latents = encode_image_to_latents(pipe, args.image, args.device, dtype)
    
    # Сохраняем latents
    latents_path = os.path.join(args.output_dir, "latents.pt")
    torch.save(latents.cpu(), latents_path)
    print(f"[INFO] Latents saved to: {latents_path}")
    
    # Декодируем обратно
    reconstructed = decode_latents_to_image(pipe, latents)
    
    # Сохраняем результат
    output_path = os.path.join(args.output_dir, "reconstructed.png")
    reconstructed.save(output_path)
    print(f"[INFO] Reconstructed image saved to: {output_path}")
    
    # Сравниваем размеры
    original = Image.open(args.image).convert("RGB")
    print(f"[INFO] Original size: {original.size}")
    print(f"[INFO] Reconstructed size: {reconstructed.size}")
    
    print(f"[INFO] Done! Check {args.output_dir}/reconstructed.png")
    print(f"[INFO] Note: reconstructed image may be slightly blurry due to VAE compression")


if __name__ == "__main__":
    main()
