import os
import json
import hashlib
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from datetime import datetime
import folder_paths
from server import PromptServer
from aiohttp import web

# Memory cache for the manual button: key = (workflow_run_id, node_id) so each workflow+node is isolated
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
                "autosave": ("BOOLEAN", {"default": False}),
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

    def cherry_pick_logic(self, images, filename_prefix, autosave, prompt=None, extra_pnginfo=None, unique_id=None):
        # 1. Stable node id and workflow-scoped cache key (so different workflows don't share cache)
        node_id = str(unique_id[0]) if isinstance(unique_id, list) else str(unique_id)
        workflow_run_id = hashlib.sha256(
            json.dumps(prompt, sort_keys=True).encode()
        ).hexdigest()[:16]
        cache_key = f"{workflow_run_id}_{node_id}"

        CHERRY_CACHE[cache_key] = {
            "images": images,
            "prefix": filename_prefix,
            "prompt": prompt,
            "extra_pnginfo": extra_pnginfo,
        }

        # 2. If autosave is on, save to output folder like a normal Save Image node
        if autosave:
            save_images_to_output(images, filename_prefix, prompt, extra_pnginfo)

        # 3. Save temp images for the node UI (include workflow_run_id so preview is per-run)
        results = []
        for i, image in enumerate(images):
            img_np = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))

            # Unique temp name to prevent caching issues across workflows
            temp_name = f"cp_temp_{cache_key}_{i}.png"
            full_path = os.path.join(folder_paths.get_temp_directory(), temp_name)
            img.save(full_path)

            results.append(
                {
                    "filename": temp_name,
                    "subfolder": "",
                    "type": "temp",
                }
            )

        # Pass workflow_run_id to frontend so Save button can use the right cache entry
        return {"ui": {"images": results, "workflow_run_id": workflow_run_id}}


def save_images_to_output(images, filename_prefix, prompt=None, extra_pnginfo=None):
    """Save images to the output folder with metadata. Used by autosave and the manual save API."""
    prefix = process_tokens(filename_prefix)
    full_output_folder, filename, counter, subfolder, filename_prefix_out = folder_paths.get_save_image_path(
        prefix,
        folder_paths.get_output_directory(),
        images[0].shape[1],
        images[0].shape[0],
    )
    os.makedirs(full_output_folder, exist_ok=True)
    for image in images:
        img_np = 255.0 * image.cpu().numpy()
        img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
        metadata = PngInfo()
        if prompt:
            metadata.add_text("prompt", json.dumps(prompt))
        if extra_pnginfo:
            for key in extra_pnginfo:
                metadata.add_text(key, json.dumps(extra_pnginfo[key]))
        file = f"{filename}_{counter:05}_.png"
        img.save(os.path.join(full_output_folder, file), pnginfo=metadata, compress_level=4)
        counter += 1


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
        workflow_run_id = json_data.get("workflow_run_id")

        if not workflow_run_id:
            return web.json_response(
                {
                    "status": "error",
                    "message": "Workflow run ID missing. Run the workflow first, then save.",
                }
            )

        cache_key = f"{workflow_run_id}_{node_id}"
        if cache_key not in CHERRY_CACHE:
            return web.json_response(
                {
                    "status": "error",
                    "message": f"Cache miss for this workflow run. Run the workflow first!",
                }
            )

        data = CHERRY_CACHE[cache_key]
        save_images_to_output(
            data["images"],
            data["prefix"],
            data["prompt"],
            data["extra_pnginfo"],
        )
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})