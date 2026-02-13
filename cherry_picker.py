import os
import json
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from datetime import datetime
import folder_paths
from server import PromptServer
from aiohttp import web

# Memory cache for the manual button
CHERRY_CACHE = {}


class CherryPicker:
    def __init__(self):
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "%date:MM-dd-yy%/ZImage"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "cherry_pick_logic"
    OUTPUT_NODE = True
    CATEGORY = "image"

    def cherry_pick_logic(self, images, filename_prefix, prompt=None, extra_pnginfo=None, unique_id=None):
        # 1. Clean the ID and update the cache (match original behavior for cache key)
        node_id = str(unique_id[0]) if isinstance(unique_id, list) else str(unique_id)

        CHERRY_CACHE[node_id] = {
            "images": images,
            "prefix": filename_prefix,
            "prompt": prompt,
            "extra_pnginfo": extra_pnginfo,
        }

        # 2. Save temp images for the node UI
        results = []
        for i, image in enumerate(images):
            img_np = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))

            # Unique temp name to prevent caching issues
            temp_name = f"cp_temp_{node_id}_{i}.png"
            full_path = os.path.join(folder_paths.get_temp_directory(), temp_name)
            img.save(full_path)

            results.append(
                {
                    "filename": temp_name,
                    "subfolder": "",
                    "type": "temp",
                }
            )

        return {"ui": {"images": results}}


def process_tokens(text):
    """Robust token processing cherry-picked from EasyUse logic."""
    now = datetime.now()
    if "%date:" in text:
        start = text.find("%date:") + 6
        end = text.find("%", start)
        if end != -1:
            date_format = text[start:end]
            # Resolves 'yy' to '26' for folder names
            fmt = (
                date_format.replace("yyyy", "%Y")
                .replace("YYYY", "%Y")
                .replace("yy", "%y")
                .replace("YY", "%y")
                .replace("MM", "%m")
                .replace("dd", "%d")
            )
            text = text[: start - 6] + now.strftime(fmt) + text[end + 1 :]

    # Restored shorthand tokens
    tokens = {
        "%year%": "%Y",
        "%month%": "%m",
        "%day%": "%d",
        "%hour%": "%H",
        "%minute%": "%M",
        "%second%": "%S",
    }
    for token, py_fmt in tokens.items():
        if token in text:
            text = text.replace(token, now.strftime(py_fmt))
    return text


@PromptServer.instance.routes.post("/cherrypicker/save")
async def save_cherry_pick(request):
    """API handler triggered by the JS button."""
    try:
        json_data = await request.json()
        node_id = str(json_data.get("node_id"))

        # Check for the images in cache
        if node_id not in CHERRY_CACHE:
            return web.json_response(
                {
                    "status": "error",
                    "message": f"Cache miss for ID {node_id}. Run the workflow first!",
                }
            )

        data = CHERRY_CACHE[node_id]
        filename_prefix = process_tokens(data["prefix"])
        images = data["images"]

        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            filename_prefix,
            folder_paths.get_output_directory(),
            images[0].shape[1],
            images[0].shape[0],
        )

        os.makedirs(full_output_folder, exist_ok=True)

        for image in images:
            img_np = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))

            # Embed metadata for workflow drag-and-drop
            metadata = PngInfo()
            if data["prompt"]:
                metadata.add_text("prompt", json.dumps(data["prompt"]))
            if data["extra_pnginfo"]:
                for key in data["extra_pnginfo"]:
                    metadata.add_text(key, json.dumps(data["extra_pnginfo"][key]))

            file = f"{filename}_{counter:05}_.png"
            img.save(os.path.join(full_output_folder, file), pnginfo=metadata, compress_level=4)
            counter += 1

        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})