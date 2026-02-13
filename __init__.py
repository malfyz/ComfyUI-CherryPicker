from .cherry_picker import CherryPicker

NODE_CLASS_MAPPINGS = {
    "CherryPicker": CherryPicker
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CherryPicker": "🍒 Cherry Picker (Save Image)"
}

# Tells ComfyUI to look in the /js/ folder for the button code
WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]