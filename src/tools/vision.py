import os
import base64
import json
from typing import Dict, Any

class VisionAnalysis:
    """
    Analyzes images using the currently configured provider's vision capabilities.
    Encodes the image as base64 and sends a multimodal request via the orchestrator.
    """

    def __init__(self):
        pass

    def analyze_image(self, image_path: str, prompt: str = "Describe this image in detail.") -> Dict[str, Any]:
        """
        Analyze an image from a local file path.
        
        Args:
            image_path: Absolute path to the image file on disk.
            prompt: Text prompt to guide the analysis.
        
        Returns:
            Dict with multimodal messages for the provider to process.
        """
        if not os.path.exists(image_path):
            return {"description": "", "error": f"Image not found: {image_path}"}

        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            ext = os.path.splitext(image_path)[1].lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }
            mime = mime_map.get(ext, "image/png")
            b64 = base64.b64encode(image_data).decode("utf-8")
            data_url = f"data:{mime};base64,{b64}"
        except Exception as e:
            return {"description": "", "error": f"Failed to read image: {e}"}

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ]

        return {
            "description": "",
            "error": None,
            "_multimodal_messages": messages
        }

    def analyze_image_from_url(self, image_url: str, prompt: str = "Describe this image in detail.") -> Dict[str, Any]:
        """
        Analyze an image from a remote URL.
        
        Args:
            image_url: URL to an image on the web.
            prompt: Text prompt to guide the analysis.
        
        Returns:
            Dict with multimodal messages for the provider to process.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]

        return {
            "description": "",
            "error": None,
            "_multimodal_messages": messages
        }
