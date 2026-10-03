# Put VoxTranslate on phones

## 1. Host it online (needed so anyone's phone can reach it)
Use any host that runs Docker (Render, Railway, Fly.io):
1. Push this folder to a GitHub repository.
2. Create a new "Web Service" from the repo (it detects the `Dockerfile`).
3. Set environment variables: `SECRET_KEY` (any long random text), and for password-reset email
   `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`.
4. Attach a persistent disk mounted at `/data` so accounts and history are not lost on redeploy.
   (Free plans without a disk reset the database on every restart.)
5. You get an https link like `https://voxtranslate.onrender.com`.

## 2. Install on a phone (no app store needed)
- **Android (Chrome):** open the link, menu (⋮) → **Install app**.
- **iPhone (Safari):** open the link, Share → **Add to Home Screen**.
  Note: iPhone browsers have limited voice-recognition support, so the Conversation mic may not work there.

## 3. Real Android app file (.apk / Play Store)
1. Go to https://www.pwabuilder.com and enter your https link.
2. Choose **Android** → download the package (APK / AAB).
3. Publishing on Google Play needs a one-time developer account fee.
This wraps the website in Chrome, so the mic, camera and voice keep working on Android.
