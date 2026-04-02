"""
AI-based Image Filtering Module
Uses CLIP for style matching and character detection
"""

import asyncio
import io
from typing import Optional

import aiohttp
import torch
from PIL import Image
from tqdm import tqdm

from config import PINTEREST_HEADERS, STYLE_PROMPTS, CHARACTERS

# Lazy load heavy models
_clip_model = None
_clip_preprocess = None
_tokenizer = None


def _load_clip():
    """Lazy load CLIP model"""
    global _clip_model, _clip_preprocess, _tokenizer

    if _clip_model is None:
        try:
            import open_clip

            print('Loading CLIP model...')
            _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32', pretrained='openai'
            )
            _tokenizer = open_clip.get_tokenizer('ViT-B-32')

            # Move to GPU if available
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            _clip_model = _clip_model.to(device)
            _clip_model.eval()

            print(f'CLIP model loaded on {device}')
        except ImportError:
            print('Warning: open_clip not installed. AI filtering disabled.')
            return None, None, None

    return _clip_model, _clip_preprocess, _tokenizer


class CLIPStyleFilter:
    """Filter images based on visual style using CLIP"""

    def __init__(self, style_prompts: list[str] = None):
        self.style_prompts = style_prompts or STYLE_PROMPTS
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self._text_features = None

    def _encode_prompts(self):
        """Pre-encode text prompts"""
        model, _, tokenizer = _load_clip()
        if model is None:
            return None

        with torch.no_grad():
            text_tokens = tokenizer(self.style_prompts).to(self.device)
            self._text_features = model.encode_text(text_tokens)
            self._text_features /= self._text_features.norm(dim=-1, keepdim=True)

        return self._text_features

    def compute_style_score(self, image: Image.Image) -> float:
        """Compute style similarity score for an image"""
        model, preprocess, _ = _load_clip()
        if model is None:
            return 0.0

        if self._text_features is None:
            self._encode_prompts()

        try:
            # Preprocess image
            img_tensor = preprocess(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                # Encode image
                image_features = model.encode_image(img_tensor)
                image_features /= image_features.norm(dim=-1, keepdim=True)

                # Compute similarity with style prompts
                similarities = (image_features @ self._text_features.T).squeeze()

                # Return max similarity across all prompts
                return similarities.max().item()
        except Exception as e:
            print(f'Error computing style score: {e}')
            return 0.0


class CharacterDetector:
    """Detect specific characters in images using CLIP"""

    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self._char_features = None
        self._char_ids = []

    def _encode_characters(self):
        """Pre-encode character descriptions"""
        model, _, tokenizer = _load_clip()
        if model is None:
            return None

        # Build character prompts
        char_prompts = []
        self._char_ids = []

        for char_id, char_data in CHARACTERS.items():
            # Create multiple prompts per character
            for name in char_data['names'][:2]:  # Use first 2 names
                for series in char_data['series'][:2]:  # Use first 2 series
                    prompt = f'{name} from {series}, chinese xianxia character'
                    char_prompts.append(prompt)
                    self._char_ids.append(char_id)

        with torch.no_grad():
            text_tokens = tokenizer(char_prompts).to(self.device)
            self._char_features = model.encode_text(text_tokens)
            self._char_features /= self._char_features.norm(dim=-1, keepdim=True)

        return self._char_features

    def detect_character(self, image: Image.Image) -> tuple[str, float]:
        """Detect which character is in the image"""
        model, preprocess, _ = _load_clip()
        if model is None:
            return '', 0.0

        if self._char_features is None:
            self._encode_characters()

        try:
            img_tensor = preprocess(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                image_features = model.encode_image(img_tensor)
                image_features /= image_features.norm(dim=-1, keepdim=True)

                similarities = (image_features @ self._char_features.T).squeeze()

                # Find best match
                best_idx = similarities.argmax().item()
                best_score = similarities[best_idx].item()
                best_char = self._char_ids[best_idx]

                # Only return if confidence is high enough
                if best_score >= 0.25:  # Threshold
                    return best_char, best_score
                return '', 0.0
        except Exception as e:
            print(f'Error detecting character: {e}')
            return '', 0.0


async def download_and_process_image(session: aiohttp.ClientSession, url: str) -> Optional[Image.Image]:
    """Download image and return PIL Image"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                data = await response.read()
                return Image.open(io.BytesIO(data)).convert('RGB')
    except Exception as e:
        pass
    return None


async def apply_ai_filters(images: list, batch_size: int = 10) -> list:
    """Apply AI filtering to images"""
    model, _, _ = _load_clip()
    if model is None:
        print('CLIP not available, skipping AI filtering')
        return images

    style_filter = CLIPStyleFilter()
    char_detector = CharacterDetector()

    async with aiohttp.ClientSession(headers=PINTEREST_HEADERS) as session:
        for i in tqdm(range(0, len(images), batch_size), desc='AI filtering'):
            batch = images[i:i + batch_size]

            for img in batch:
                url = img.get('url', '')
                if not url:
                    continue

                pil_image = await download_and_process_image(session, url)
                if pil_image is None:
                    continue

                # Compute style score
                style_score = style_filter.compute_style_score(pil_image)
                img['style_score'] = style_score

                # Detect character
                char_id, char_score = char_detector.detect_character(pil_image)
                if char_id:
                    img['ai_detected_character'] = char_id
                    img['ai_character_confidence'] = char_score

            await asyncio.sleep(0.5)  # Rate limit

    return images


if __name__ == '__main__':
    # Test AI filter
    async def test():
        print('Testing AI filter...')

        # Test with a sample image URL
        test_images = [
            {'id': '1', 'url': 'https://i.pinimg.com/originals/ab/cd/ef/sample.jpg'},
        ]

        # Note: Would need real URLs to test properly
        print('AI filter module loaded successfully')

    asyncio.run(test())
