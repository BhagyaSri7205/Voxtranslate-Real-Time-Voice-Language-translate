"""VoxTranslate web server. Reuses the existing backend/ and database/ code unchanged."""
import io, os, sys, base64
from datetime import timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, request, session, jsonify, send_file, send_from_directory, make_response
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
from gtts import gTTS
from backend import auth
from backend.translation import LANGUAGES, translate_text, is_translation_error
from backend.ocr import extract_text, OCRNotAvailableError
from database.database import create_database, save_translation, get_history, clear_history

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.update(SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("PRODUCTION")),
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30))
_key = ROOT / ".secret_key"
if not _key.exists():
    _key.write_text(os.urandom(24).hex())
app.secret_key = os.environ.get("SECRET_KEY", _key.read_text())
create_database()


def need_login(fn):
    def wrap(*a, **k):
        if "user" not in session:
            return jsonify(ok=False, message="Please log in."), 401
        return fn(*a, **k)
    wrap.__name__ = fn.__name__
    return wrap


def body():
    return request.get_json(silent=True) or {}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/sw.js")
def service_worker():
    r = make_response(send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript"))
    r.headers["Cache-Control"] = "no-cache"
    r.headers["Service-Worker-Allowed"] = "/"
    return r


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


# ---------- auth ----------
@app.post("/api/register")
def register():
    d = body()
    ok, msg = auth.signup(d.get("username", ""), d.get("email", ""), d.get("password", ""))
    return jsonify(ok=ok, message=msg)


@app.post("/api/login")
def login():
    d = body()
    ok, msg = auth.login(d.get("username", ""), d.get("password", ""))
    if ok:
        session.permanent = True
        session["user"] = d["username"].strip()
    return jsonify(ok=ok, message=msg, user=session.get("user"))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    return jsonify(user=session.get("user"))


@app.post("/api/forgot")
def forgot():
    ok, msg, uid = auth.request_password_reset(body().get("email", ""))
    return jsonify(ok=ok, message=msg, user_id=uid)


@app.post("/api/verify-otp")
def verify_otp():
    d = body()
    ok, msg = auth.verify_password_reset_otp(int(d.get("user_id", 0)), d.get("otp", ""))
    return jsonify(ok=ok, message=msg)


@app.post("/api/reset")
def reset():
    d = body()
    ok, msg = auth.reset_password(int(d.get("user_id", 0)), d.get("password", ""))
    return jsonify(ok=ok, message=msg)


# ---------- features ----------
@app.get("/api/diag")
def diag():
    """Open /api/diag in a browser to see which translation services work from THIS server."""
    from backend import translation as T
    out = {}
    for label, fn in T._PROVIDERS:
        if label == "Google Cloud API" and not os.environ.get("GOOGLE_TRANSLATE_API_KEY"):
            continue
        try:
            out[label] = "OK: " + str(fn("Hello, how are you?", "en", "hi"))[:60]
        except Exception as e:
            out[label] = f"FAILED: {type(e).__name__}: {str(e)[:80]}"
    return jsonify(out)


@app.get("/api/languages")
def languages():
    return jsonify(LANGUAGES)


@app.post("/api/translate")
@need_login
def translate():
    d = body()
    text, src, dst = d.get("text", "").strip(), d.get("source", "auto"), d.get("target", "en")
    if not text:
        return jsonify(ok=False, message="Enter some text first.")
    out = translate_text(text, src, dst)
    if is_translation_error(out):
        return jsonify(ok=False, message=out, retry=True)
    if d.get("save", True):
        names = {v: k for k, v in LANGUAGES.items()}
        save_translation("Auto Detect" if src == "auto" else names.get(src, src),
                         names.get(dst, dst), text, out, session["user"])
    return jsonify(ok=True, text=out)


@app.post("/api/save")
@need_login
def save():
    """Save a translation that the browser itself fetched (used when the server's IP is limited)."""
    d = body()
    names = {v: k for k, v in LANGUAGES.items()}
    src, dst = d.get("source", "auto"), d.get("target", "en")
    save_translation("Auto Detect" if src == "auto" else names.get(src, src), names.get(dst, dst),
                     d.get("text", ""), d.get("out", ""), session["user"])
    return jsonify(ok=True)


@app.get("/api/tts")
@need_login
def tts():
    text, lang = request.args.get("text", "").strip(), request.args.get("lang", "en")
    if not text:
        return "", 400
    buf = io.BytesIO()
    try:
        gTTS(text=text, lang=lang).write_to_fp(buf)
    except Exception as e:
        return jsonify(ok=False, message=str(e)), 502
    buf.seek(0)
    return send_file(buf, mimetype="audio/mpeg")


@app.post("/api/ocr")
@need_login
def ocr():
    try:
        raw = base64.b64decode(body().get("image", "").split(",")[-1])
        text = extract_text(Image.open(io.BytesIO(raw)).convert("RGB"), body().get("lang"))
        return jsonify(ok=True, text=text.strip())
    except OCRNotAvailableError as e:
        return jsonify(ok=False, message=str(e), fallback=True)
    except Exception as e:
        return jsonify(ok=False, message=f"OCR failed: {e}", fallback=True)


@app.get("/api/history")
@need_login
def history():
    rows = get_history(session["user"])
    return jsonify([list(r) for r in rows])


@app.delete("/api/history")
@need_login
def del_history():
    clear_history(session["user"])
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n VoxTranslate running at http://127.0.0.1:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
