# ⚕ MIRA — Deployment Guide

Three ways to run MIRA. Pick one.

---

## 🐳 Option A — Docker (Easiest, works everywhere)

**Requires:** Docker Desktop installed

```bash
# Clone / unzip the project, then:
docker-compose up --build
```

Open → **http://localhost:5000**
Admin → **http://localhost:5000/admin**

That's it. One command. The database persists in a Docker volume.

**Other useful commands:**
```bash
docker-compose up --build -d   # run in background
docker-compose logs -f         # watch logs
docker-compose down            # stop
docker-compose down -v         # stop + wipe database
```

**Without docker-compose:**
```bash
docker build -t mira .
docker run -p 5000:5000 -v mira_data:/data -e JWT_SECRET=your-secret mira
```

---

## ☁️ Option B — Render (Free cloud hosting)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "MIRA initial deploy"
# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/mira-app.git
git push -u origin main
```

### Step 2 — Deploy on Render
1. Go to **https://render.com** → New → **Blueprint**
2. Connect your GitHub repo
3. Render detects `render.yaml` automatically and configures everything

**Or manually (New → Web Service):**
| Setting | Value |
|---|---|
| Runtime | Python |
| Build Command | `bash build.sh` |
| Start Command | `bash start.sh` |
| Plan | Free |

### Step 3 — Set Environment Variables
In Render dashboard → Environment:
| Key | Value |
|---|---|
| `JWT_SECRET` | any long random string |
| `DATA_DIR` | `/data` |

### Step 4 — Add Persistent Disk
Render dashboard → Disks → Add Disk:
| Setting | Value |
|---|---|
| Name | `mira-data` |
| Mount Path | `/data` |
| Size | 1 GB |

> ⚠️ Free plan spins down after 15 min inactivity. First request after sleep takes ~30s. Upgrade to Starter ($7/mo) to keep it always on.

---

## 💻 Option C — Local (No Docker)

```bash
# Terminal 1 — Backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python train_model.py           # once only
python app.py

# Terminal 2 — Frontend
cd frontend
npm install
npm start
```

Backend: http://localhost:5000
Frontend: http://localhost:3000
Admin: http://localhost:3000/admin

---

## 🔐 Admin Credentials

| Username | Password |
|---|---|
| `admin` | `admin123` |

Change the password by updating the hash in your database after first login.

---

## 📁 Project Structure

```
MIRA_Render/
├── Dockerfile              ← Multi-stage Docker build
├── docker-compose.yml      ← One-command local Docker
├── render.yaml             ← Render blueprint (auto-detects)
├── build.sh                ← Render build step
├── start.sh                ← Render start command
├── backend/
│   ├── app.py              ← Flask API + serves React build
│   ├── train_model.py      ← ML model training
│   ├── model.pkl           ← Pre-trained model (included)
│   ├── features.json
│   └── requirements.txt    ← Includes gunicorn
└── frontend/
    ├── src/                ← React source files
    └── public/
```

---

## 🌐 URLs (after deploy)

| Page | URL |
|---|---|
| Patient Form | `https://your-app.onrender.com/` |
| Admin Console | `https://your-app.onrender.com/admin` |
| Health Check | `https://your-app.onrender.com/health` |
