# Deploying Zora on Termux + Cloudflare Tunnel

> **Target:** `https://zora.crackery.in`  
> **Server:** Android phone running Termux  
> **Tunnel:** Cloudflare Tunnel (cloudflared)

---

## Prerequisites

- Android phone with [Termux](https://f-droid.org/en/packages/com.termux/) installed (use F-Droid, not Play Store)
- Cloudflare account with `crackery.in` domain added
- Your Zora project files

---

## Step 1 — Set up Termux

```bash
# Update packages
pkg update && pkg upgrade -y

# Install essentials
pkg install python git ffmpeg openssh -y

# Install build tools (needed for some pip packages)
pkg install build-essential libffi openssl -y

# Optional: prevent phone from sleeping
termux-wake-lock
```

---

## Step 2 — Get the project onto your phone

**Option A: Git clone (recommended)**
```bash
# Clone your repo
git clone <your-repo-url> ~/zora
cd ~/zora/zora
```

**Option B: Transfer from Mac**
```bash
# On Mac — zip and transfer
cd /Users/dilshad/Desktop/Projects/zora
tar czf zora.tar.gz zora/

# Transfer via scp (need openssh on Termux, run `sshd` first)
scp zora.tar.gz <phone-ip>:~/

# On Termux
cd ~
tar xzf zora.tar.gz
cd zora/zora
```

---

## Step 3 — Install Python dependencies

```bash
cd ~/zora/zora

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> **Note:** If `pip install` fails on some packages, try:
> ```bash
> LDFLAGS="-L/data/data/com.termux/files/usr/lib" \
> CFLAGS="-I/data/data/com.termux/files/usr/include" \
> pip install -r requirements.txt
> ```

---

## Step 4 — Configure environment

Create the `.env` file:

```bash
cat > .env << 'EOF'
# === Server ===
ZORA_HOST=127.0.0.1
ZORA_PORT=5001
FLASK_ENV=production

# === Security (REQUIRED — generate a strong key) ===
SECRET_KEY=CHANGE_ME_run_python3_-c_"import secrets; print(secrets.token_hex(32))"

# === Admin account (created on first run) ===
ZORA_ADMIN_EMAIL=your-email@example.com
ZORA_ADMIN_PASSWORD=your-strong-password-here

# === Google OAuth (get from https://console.cloud.google.com/apis/credentials) ===
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# === SMTP for password reset (Gmail example) ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password

# === Base URL (your public domain) ===
ZORA_BASE_URL=https://zora.crackery.in
EOF
```

**Generate a proper SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Copy the output and paste it as SECRET_KEY in .env
```

**Important:** Edit `.env` with your real credentials:
```bash
nano .env
```

---

## Step 5 — Google OAuth setup

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create or edit your OAuth 2.0 Client ID
3. Add these **Authorized redirect URIs**:
   ```
   https://zora.crackery.in/api/auth/google/callback
   ```
4. Under **Authorized JavaScript origins**, add:
   ```
   https://zora.crackery.in
   ```
5. Copy the Client ID and Client Secret into your `.env`

---

## Step 6 — Initialize the database

```bash
cd ~/zora/zora
source venv/bin/activate

# Delete old database if it exists (fresh start)
rm -f data.db

# Quick test — this creates the DB and admin account
python -c "from app import create_app; app = create_app(); print('✅ App initialized')"
```

You should see:
```
✅ Admin account created for your-email@example.com
✅ App initialized
```

---

## Step 7 — Test locally

```bash
# Quick test run
python run.py
```

Visit `http://localhost:5001` in your phone's browser. Login with your admin credentials. Press Ctrl+C to stop.

---

## Step 8 — Install and configure Cloudflare Tunnel

```bash
# Install cloudflared
pkg install cloudflared -y

# If not available via pkg, download the binary:
# curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o $PREFIX/bin/cloudflared
# chmod +x $PREFIX/bin/cloudflared

# Authenticate with Cloudflare
cloudflared tunnel login
# This opens a browser — select crackery.in domain

# Create a tunnel
cloudflared tunnel create zora
# Note the tunnel UUID it prints (e.g., abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

# Route DNS
cloudflared tunnel route dns zora zora.crackery.in
```

Create the cloudflared config:

```bash
mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << EOF
tunnel: <YOUR-TUNNEL-UUID>
credentials-file: /data/data/com.termux/files/home/.cloudflared/<YOUR-TUNNEL-UUID>.json

ingress:
  - hostname: zora.crackery.in
    service: http://127.0.0.1:5001
  - service: http_status:404
EOF
```

Replace `<YOUR-TUNNEL-UUID>` with the actual UUID from the `tunnel create` step.

---

## Step 9 — Create startup script

```bash
cat > ~/start-zora.sh << 'SCRIPT'
#!/bin/bash
# Zora Production Startup Script

cd ~/zora/zora
source venv/bin/activate

# Prevent phone from sleeping
termux-wake-lock

echo "🎵 Starting Zora..."

# Start gunicorn (production WSGI server) in background
gunicorn \
  --bind 127.0.0.1:5001 \
  --workers 2 \
  --threads 2 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  --daemon \
  "run:app"

echo "✅ Gunicorn started on port 5001"

# Start cloudflared tunnel
echo "🌐 Starting Cloudflare tunnel..."
cloudflared tunnel run zora &

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  🎵 Zora is live!                     ║"
echo "║  🌐 https://zora.crackery.in          ║"
echo "╚═══════════════════════════════════════╝"
echo ""
echo "To stop: ~/stop-zora.sh"
SCRIPT

chmod +x ~/start-zora.sh

# Create logs directory
mkdir -p ~/zora/zora/logs
```

Create a stop script:

```bash
cat > ~/stop-zora.sh << 'SCRIPT'
#!/bin/bash
echo "Stopping Zora..."
pkill -f gunicorn
pkill -f cloudflared
termux-wake-unlock
echo "✅ Stopped"
SCRIPT

chmod +x ~/stop-zora.sh
```

---

## Step 10 — Launch!

```bash
~/start-zora.sh
```

Visit **https://zora.crackery.in** — you should see the login page.

---

## Auto-start on Termux boot (optional)

```bash
mkdir -p ~/.termux/boot

cat > ~/.termux/boot/start-zora.sh << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
sleep 10
~/start-zora.sh
SCRIPT

chmod +x ~/.termux/boot/start-zora.sh
```

> Requires the [Termux:Boot](https://f-droid.org/en/packages/com.termux.boot/) app from F-Droid.

---

## Setting up Google OAuth (step-by-step)

### 1. Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Name it `Zora` → **Create**
4. Make sure `Zora` is selected as the active project

### 2. Enable the Google OAuth API

1. Go to **APIs & Services → Library**
2. Search for **"Google Identity"** or skip this (OAuth works without explicitly enabling)

### 3. Configure the OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** → **Create**
3. Fill in:
   - **App name:** `Zora`
   - **User support email:** your email
   - **Developer contact email:** your email
4. Click **Save and Continue**
5. **Scopes** → Click **Add or Remove Scopes** → add:
   - `openid`
   - `email`
   - `profile`
6. Click **Save and Continue**
7. **Test users** → Add your Google email(s) you'll use to login
8. Click **Save and Continue** → **Back to Dashboard**

> ⚠️ While in "Testing" mode, only test users can login. To allow anyone:  
> Go to **OAuth consent screen → Publishing status → Publish App**

### 4. Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `Zora Web`
5. **Authorized JavaScript origins:**
   ```
   https://zora.crackery.in
   http://localhost:5001
   ```
6. **Authorized redirect URIs:**
   ```
   https://zora.crackery.in/api/auth/google/callback
   http://localhost:5001/api/auth/google/callback
   ```
7. Click **Create**
8. Copy the **Client ID** and **Client Secret**

### 5. Add to your `.env`

```env
GOOGLE_CLIENT_ID=123456789-xxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxx
```

### 6. Restart Zora

```bash
~/stop-zora.sh
~/start-zora.sh
```

The "Continue with Google" button on the login page should now work.

---

## Setting up Forgot Password email (SMTP)

### Option A: Gmail (easiest)

#### 1. Enable 2-Step Verification

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Under **"How you sign in to Google"** → enable **2-Step Verification**

#### 2. Create an App Password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. App name: `Zora`
3. Click **Create**
4. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

#### 3. Add to your `.env`

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
ZORA_BASE_URL=https://zora.crackery.in
```

> Remove the spaces from the app password when pasting.

---

### Option B: Outlook / Hotmail

```env
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-outlook-password
ZORA_BASE_URL=https://zora.crackery.in
```

---

### Option C: Custom domain email (Zoho, etc.)

```env
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USER=you@crackery.in
SMTP_PASSWORD=your-password
ZORA_BASE_URL=https://zora.crackery.in
```

---

### Testing the forgot password flow

1. Restart Zora after updating `.env`
2. Go to `https://zora.crackery.in`
3. Click **"Forgot password?"** on the login page
4. Enter your registered email → click **Send Reset Link**
5. Check your inbox for the email with a reset link
6. Click the link → set a new password → login

**If SMTP isn't configured,** the reset link prints to the terminal:
```
============================================================
  PASSWORD RESET LINK (SMTP not configured)
  User: admin@test.com
  Link: https://zora.crackery.in/?reset_token=abc123...
  Expires in 1 hour
============================================================
```
You can copy-paste that link into your browser — useful for development.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip install` fails | `pkg install build-essential libffi openssl` |
| ffmpeg not found | `pkg install ffmpeg` |
| DB locked errors | Reduce gunicorn workers to 1: `--workers 1` |
| Phone sleeps / kills process | Run `termux-wake-lock` and disable battery optimization for Termux |
| Cloudflared won't start | Check `~/.cloudflared/config.yml` has correct UUID |
| Google OAuth redirect error | Verify redirect URI in Google Console matches exactly |
| 502 after reboot | Run `~/start-zora.sh` again |

---

## Updating Zora

```bash
~/stop-zora.sh
cd ~/zora/zora
git pull
source venv/bin/activate
pip install -r requirements.txt
~/start-zora.sh
```
