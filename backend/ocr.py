import platform

from PIL import Image, ImageOps

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


class CameraError(Exception):
    """Raised when the webcam can't be opened or read from."""
    pass


class OCRNotAvailableError(Exception):
    """Raised when pytesseract or the Tesseract OCR engine isn't available."""
    pass


def check_dependencies():
    """Raises a clear error early if either dependency is missing."""
    if cv2 is None:
        raise CameraError(
            "OpenCV is not installed. Run: pip install opencv-python"
        )
    if pytesseract is None:
        raise OCRNotAvailableError(
            "pytesseract is not installed. Run: pip install pytesseract"
        )


def open_camera(index=0):
    """
    Opens the default webcam. Raises CameraError with a clear message on
    failure.

    On Windows, cv2's default backend (MSMF) is frequently slow to open
    or opens "successfully" while silently failing to deliver frames from
    common webcams — this is one of the most common causes of camera
    translate just not working. DirectShow (CAP_DSHOW) is much more
    reliable there, so it's tried first, with the platform default kept
    as a fallback for machines/webcams where DSHOW isn't available.
    """
    if cv2 is None:
        raise CameraError("OpenCV is not installed. Run: pip install opencv-python")

    backends = []
    if platform.system() == "Windows":
        backends.append(cv2.CAP_DSHOW)
    backends.append(cv2.CAP_ANY)

    cap = None
    for backend in backends:
        candidate = cv2.VideoCapture(index, backend)
        if candidate.isOpened():
            # Some backends report "opened" before the very first frame is
            # actually available — confirm we can read a frame too.
            ok, _ = candidate.read()
            if ok:
                cap = candidate
                break
        candidate.release()

    if cap is None:
        raise CameraError(
            "Could not open the camera. Check that a webcam is connected, "
            "that no other app is currently using it, and that this app has "
            "camera permission."
        )

    # Many webcams default to a low capture resolution (often 640x480 or
    # less). That's fine for a single short word, but a multi-line
    # paragraph packed into a low-res frame leaves very few pixels of
    # height per line, which is one of the most common reasons OCR reads
    # a single line fine but garbles or drops a paragraph. Requesting a
    # higher resolution here (the camera will silently clamp to its best
    # supported mode if 1280x720 isn't available) gives Tesseract much
    # more detail to work with, especially for multi-line captures.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    return cap


def read_frame(cap):
    """Reads one frame from an open camera and returns it as a PIL Image (RGB)."""
    ret, frame = cap.read()
    if not ret or frame is None:
        raise CameraError("Failed to read a frame from the camera.")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _preprocess_for_ocr(pil_image):
    """
    Cleans up a raw camera frame so Tesseract has a realistic chance of
    reading it. Camera frames are low-contrast, often small, and slightly
    soft compared to a scanned document — feeding them to Tesseract
    untouched (what the previous version did) is the main reason text
    that's perfectly readable to a person gets detected as empty. This
    upscales small frames, converts to grayscale, denoises, and binarizes
    with an adaptive threshold so text edges stand out clearly.
    """
    if cv2 is None or np is None:
        gray = ImageOps.grayscale(pil_image)
        return ImageOps.autocontrast(gray)

    frame = np.array(pil_image.convert("RGB"))
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

    # Upscale small/low-res frames — Tesseract does much better once text
    # is at least ~30px tall.
    h, w = gray.shape
    longest_side = max(h, w)
    if longest_side < 1000:
        scale = 1000 / longest_side
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(gray)


_lang_cache = None


def _ocr_lang_string():
    """
    Builds the Tesseract `lang` string to use, from whichever of this
    app's supported languages actually have traineddata installed.

    The previous version never passed `lang` at all, which silently
    pins Tesseract to English-only (`eng`) even though this app
    translates Telugu, Hindi, Tamil, and many other languages — so a
    photo of non-English text would OCR as garbage or nothing. This
    detects what's actually installed and includes all of it, falling
    back to `eng` alone if detection fails or nothing else is installed.
    """
    global _lang_cache
    if _lang_cache is not None:
        return _lang_cache

    wanted = {
        "eng", "hin", "tel", "tam", "kan", "mal", "ben", "mar", "guj",
        "pan", "urd", "kor", "jpn", "chi_sim", "fra", "deu", "spa",
        "rus", "ara", "por", "ita",
    }
    try:
        installed = set(pytesseract.get_languages(config=""))
        usable = [code for code in wanted if code in installed] or ["eng"]
    except Exception:
        usable = ["eng"]

    _lang_cache = "+".join(usable)
    return _lang_cache


_TESS = {"en": "eng", "hi": "hin", "te": "tel", "ta": "tam", "kn": "kan", "ml": "mal",
         "bn": "ben", "mr": "mar", "gu": "guj", "pa": "pan", "ur": "urd", "ko": "kor",
         "ja": "jpn", "zh-CN": "chi_sim", "fr": "fra", "de": "deu", "es": "spa",
         "ru": "rus", "ar": "ara", "pt": "por", "it": "ita"}


def _fit(img):
    """Resize so the longest side is 1400-2000px (Tesseract reads best at that size)."""
    w, h = img.size
    m = max(w, h)
    k = 1400 / m if m < 1400 else (2000 / m if m > 2200 else 1)
    return img if k == 1 else img.resize((int(w * k), int(h * k)), Image.LANCZOS)


def _read(img, lang, psm):
    """One OCR pass -> (text, score). Low-confidence words are dropped as noise."""
    d = pytesseract.image_to_data(img, lang=lang, config=f"--oem 3 --psm {psm}",
                                  output_type=pytesseract.Output.DICT)
    lines, score = {}, 0.0
    for i, w in enumerate(d["text"]):
        w = (w or "").strip()
        try:
            c = float(d["conf"][i])
        except (TypeError, ValueError):
            c = -1
        if not w or c < 35:
            continue
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(w)
        score += c
    return "\n".join(" ".join(v) for _, v in sorted(lines.items())), score


def extract_text(pil_image, lang_hint=None):
    """
    Runs OCR on a PIL Image and returns the extracted text (may be empty).
    Tries a few image/layout variants and keeps the most confident reading.
    `lang_hint` is an app language code (e.g. "hi") for the language in the photo.
    """
    if pytesseract is None:
        raise OCRNotAvailableError("pytesseract is not installed. Run: pip install pytesseract")
    try:
        try:
            installed = set(pytesseract.get_languages(config=""))
        except pytesseract.TesseractNotFoundError:
            raise
        except Exception:
            installed = {"eng"}
        hint = _TESS.get(lang_hint or "")
        langs = []
        if hint and hint in installed:
            langs.append(hint if hint == "eng" or "eng" not in installed else hint + "+eng")
        langs.append(_ocr_lang_string())
        langs = list(dict.fromkeys(langs))

        base = _fit(pil_image.convert("RGB"))
        gray = ImageOps.autocontrast(ImageOps.grayscale(base))
        plans = [(gray, langs[0], 6), (gray, langs[0], 3), (_preprocess_for_ocr(base), langs[0], 6)]
        if len(langs) > 1:
            plans.append((gray, langs[1], 6))

        best, best_score = "", 0.0
        for img, lang, psm in plans:
            text, score = _read(img, lang, psm)
            if score > best_score:
                best, best_score = text, score
            if best_score >= 150:   # clearly a good reading, stop early
                break
        return best.strip()

    except pytesseract.TesseractNotFoundError:
        raise OCRNotAvailableError(
            "The Tesseract OCR engine itself isn't installed or isn't on your PATH.\n"
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki")
    except OCRNotAvailableError:
        raise
    except Exception as e:
        raise OCRNotAvailableError(f"OCR failed: {e}")
