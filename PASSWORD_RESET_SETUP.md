# VoxTranslate Password Reset Setup

The Login/Register screen now includes **Forgot password?**.

## How the recovery flow works

1. The user clicks **Forgot password?**
2. They enter the email address used during registration.
3. VoxTranslate generates a 6-digit OTP.
4. The OTP is emailed to that address.
5. The OTP is valid for 10 minutes and has a maximum of 5 verification attempts.
6. After successful verification, the user creates a new password.
7. The app returns to the Login screen.

## Email configuration

The app uses SMTP. No real email password is stored in the source code.

1. Copy `.env.example` to a new file named `.env`.
2. Put your email SMTP details in `.env`.

For Gmail:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SMTP_FROM=your-email@gmail.com
```

For Gmail, use a **Google App Password**, not your normal Gmail password.

For another email provider, replace `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD` with that provider's SMTP settings.

## Install/update packages

From the `VoxTranslate_upgraded` folder:

```text
pip install -r requirements.txt
```

## Run

```text
python main.py
```

## Important database change

Older VoxTranslate databases are automatically upgraded when the app starts. The `users` table gets an email field and a new `password_reset_otps` table is created.

Users who registered before this feature was added will need an email address associated with their account before password recovery can work for that account. New registrations require an email address.
