# VoxTranslate (Web)

## Run
1. Double-click `run_web.bat` (Mac/Linux: `./run_web.sh`), or in the VS Code terminal:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements-web.txt
   python web/server.py
   ```
2. Open http://127.0.0.1:5000 in Chrome or Edge (press Ctrl+F5 after updates).

## Notes
- Password-reset emails: copy `.env.example` to `.env` and fill in SMTP details (see `PASSWORD_RESET_SETUP.md`).
- Camera Translate needs Tesseract OCR installed on the PC running the server.
- Camera and mic work on `localhost` or https.
- Accounts and history are stored in `voxtranslate.db`.
- Hosting: a `Procfile` is included (`gunicorn --chdir web server:app`).

## Folders
- `web/` - Flask server and web page
- `backend/` - translation, login and OCR logic
- `database/` - SQLite code

## Mobile app
The site is an installable app (PWA) with a phone layout and bottom menu. See `DEPLOY_AND_INSTALL.md`.
History is now private per user.

## Check translation on your network
Run: python check_translation.py
