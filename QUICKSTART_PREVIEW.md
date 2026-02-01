# Quick Start Guide - Preview URLs

## Choose Your Method

### 🚀 Fastest: ngrok (< 1 minute)
```bash
./preview_with_ngrok.sh
```
**Result**: Get a public URL instantly  
**Best for**: Quick demos, sharing with colleagues

---

### 🐳 Docker Compose (< 2 minutes)
```bash
docker compose up
```
**Result**: Production-like local environment  
**Best for**: Testing deployment configuration

---

### ☁️ Cloud Deploy: Railway (< 5 minutes)
1. Visit [railway.app](https://railway.app/)
2. Sign in with GitHub
3. Click "New Project" → "Deploy from GitHub"
4. Select this repo
5. ✅ Get your URL: `https://your-app.railway.app`

**Best for**: Persistent preview URLs, PR testing

---

### ☁️ Cloud Deploy: Render (< 5 minutes)
1. Visit [render.com](https://render.com/)
2. Sign in with GitHub
3. New → Web Service
4. Connect this repo
5. ✅ Get your URL: `https://your-app.onrender.com`

**Best for**: Free hosting (with cold starts)

---

## Testing Your Preview URL

```bash
# Save your preview URL
PREVIEW="https://your-preview-url.com"

# Test it
curl $PREVIEW/
curl "$PREVIEW/retractions?year=2025&page_size=5"
curl "$PREVIEW/authors?limit=10"

# Or visit in browser
open "$PREVIEW/docs"
```

---

## Troubleshooting

**API not starting?**
```bash
# Check database exists
ls -la api/*.db

# Reinitialize if needed
python -m api.database
```

**Port already in use?**
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

**Docker build failing?**
```bash
# Clean build
docker compose down -v
docker compose build --no-cache
docker compose up
```

---

## Need More Help?

- 📖 Full guide: [PREVIEW_TESTING.md](PREVIEW_TESTING.md)
- 🚀 Deployment options: [DEPLOY.md](DEPLOY.md)
- 📚 API docs: [API_README.md](API_README.md)
- 💡 Examples: [EXAMPLES.md](EXAMPLES.md)
