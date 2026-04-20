import urllib.parse as _urlparse

# Trigger fraze za generisanje slika (EN + SR)
IMAGE_TRIGGERS = [
    "generate image", "create image", "make image", "draw me", "draw a",
    "generate a picture", "create a picture", "make a picture",
    "image of", "picture of", "photo of",
    "napravi sliku", "generiši sliku", "generisi sliku", "nacrtaj",
    "kreiraj sliku", "napravi mi sliku", "generisi mi sliku",
    "generate an image", "create an image", "make an image",
    "napravi mi", "generisi mi", "generiši mi",
]


def needs_image(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in IMAGE_TRIGGERS)


def extract_image_prompt(text: str) -> str:
    low = text.lower()
    for trigger in sorted(IMAGE_TRIGGERS, key=len, reverse=True):
        if trigger in low:
            idx = low.index(trigger) + len(trigger)
            rest = text[idx:].strip().lstrip(":.,").strip()
            if rest:
                return rest
    return text


def generate_image_url(prompt: str) -> str:
    encoded = _urlparse.quote(prompt)
    return f"/api/image?prompt={encoded}"
