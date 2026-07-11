"""
Обработка изображений для img2img подготовки.
Ресайз, кроп, нормализация разрешения.
"""
from PIL import Image
import os


def load_image(path: str) -> Image.Image:
    """Загружает изображение из файла"""
    return Image.open(path).convert("RGB")


def get_image_info(image: Image.Image, path: str) -> dict:
    """Возвращает информацию об изображении"""
    return {
        "width": image.width,
        "height": image.height,
        "format": image.format or "Unknown",
        "path": path
    }


def parse_preset(preset_text: str) -> tuple[int, int]:
    """Парсит пресет из текста ComboBox"""
    # "1024×1024 (квадрат)" → (1024, 1024)
    size_part = preset_text.split(" ")[0]
    width, height = map(int, size_part.replace("×", "x").split("x"))
    return width, height


def crop_center(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Center crop: вырезает центр изображения"""
    src_width, src_height = image.size
    src_aspect = src_width / src_height
    target_aspect = target_width / target_height
    
    if src_aspect > target_aspect:
        # Исходное шире — обрезаем по бокам
        new_width = int(src_height * target_aspect)
        offset = (src_width - new_width) // 2
        box = (offset, 0, offset + new_width, src_height)
    else:
        # Исходное выше — обрезаем сверху/снизу
        new_height = int(src_width / target_aspect)
        offset = (src_height - new_height) // 2
        box = (0, offset, src_width, offset + new_height)
    
    cropped = image.crop(box)
    return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)


def crop_letterbox(image: Image.Image, target_width: int, target_height: int, 
                   bg_color=(0, 0, 0)) -> Image.Image:
    """Letterbox: добавляет поля для сохранения пропорций"""
    src_width, src_height = image.size
    src_aspect = src_width / src_height
    target_aspect = target_width / target_height
    
    if src_aspect > target_aspect:
        # Исходное шире — масштабируем по ширине, добавляем поля сверху/снизу
        new_width = target_width
        new_height = int(target_width / src_aspect)
    else:
        # Исходное выше — масштабируем по высоте, добавляем поля по бокам
        new_height = target_height
        new_width = int(target_height * src_aspect)
    
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Создаём чёрный фон
    result = Image.new("RGB", (target_width, target_height), bg_color)
    
    # Вставляем resized в центр
    offset_x = (target_width - new_width) // 2
    offset_y = (target_height - new_height) // 2
    result.paste(resized, (offset_x, offset_y))
    
    return result


def crop_stretch(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Stretch: растягивает изображение (может исказить пропорции)"""
    return image.resize((target_width, target_height), Image.Resampling.LANCZOS)


def normalize_to_multiple_of_8(image: Image.Image) -> Image.Image:
    """Убеждается, что размеры кратны 8"""
    width, height = image.size
    new_width = (width // 8) * 8
    new_height = (height // 8) * 8
    
    if new_width != width or new_height != height:
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return image


def process_image(image: Image.Image, target_width: int, target_height: int, 
                  crop_mode: str) -> Image.Image:
    """Основная функция обработки"""
    if crop_mode == "center":
        result = crop_center(image, target_width, target_height)
    elif crop_mode == "letterbox":
        result = crop_letterbox(image, target_width, target_height)
    elif crop_mode == "stretch":
        result = crop_stretch(image, target_width, target_height)
    else:
        raise ValueError(f"Unknown crop mode: {crop_mode}")
    
    # Финальная проверка кратности 8
    result = normalize_to_multiple_of_8(result)
    return result


def save_processed_image(image: Image.Image, output_dir: str, 
                         original_path: str) -> str:
    """Сохраняет обработанное изображение"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Формируем имя файла
    base_name = os.path.splitext(os.path.basename(original_path))[0]
    width, height = image.size
    output_name = f"{base_name}_{width}x{height}.png"
    output_path = os.path.join(output_dir, output_name)
    
    # Если файл уже существует, добавляем суффикс
    counter = 1
    while os.path.exists(output_path):
        output_name = f"{base_name}_{width}x{height}_{counter}.png"
        output_path = os.path.join(output_dir, output_name)
        counter += 1
    
    image.save(output_path, "PNG")
    return output_path
