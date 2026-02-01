# Testing with Preview URLs

This guide explains multiple ways to test the Retraction Watch API using publicly accessible preview URLs.

## Option 1: Local Testing with ngrok (Quickest)

[ngrok](https://ngrok.com/) creates a secure tunnel to your localhost, providing a public URL for testing.

### Steps:

1. **Install ngrok**:
   ```bash
   # macOS
   brew install ngrok/ngrok/ngrok
   
   # Linux
   curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
     sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
     echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
     sudo tee /etc/apt/sources.list.d/ngrok.list && \
     sudo apt update && sudo apt install ngrok
   
   # Or download from https://ngrok.com/download
   ```

2. **Start the API locally**:
   ```bash
   ./start_api.sh
   ```

3. **Create a tunnel** (in a new terminal):
   ```bash
   ngrok http 8000
   ```

4. **Get your preview URL**:
   ngrok will display a URL like: `https://abc123.ngrok-free.app`
   
   You can now share this URL for testing:
   ```bash
   # Test the preview URL
   curl https://abc123.ngrok-free.app/
   curl https://abc123.ngrok-free.app/retractions?year=2025&page_size=5
   ```

5. **View requests**: Visit http://127.0.0.1:4040 to see all requests in the ngrok web interface

### ngrok Features:
- ✅ Free tier available
- ✅ HTTPS by default
- ✅ Request inspection UI
- ✅ Works with any platform
- ⚠️ URL changes each time (persistent URLs require paid plan)

---

## Option 2: Docker Compose Deployment

Use docker-compose for a production-like local environment.

### Steps:

1. **Start with docker-compose**:
   ```bash
   docker-compose up -d
   ```

2. **Check health**:
   ```bash
   docker-compose ps
   curl http://localhost:8000/
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f api
   ```

4. **Stop**:
   ```bash
   docker-compose down
   ```

---

## Option 3: Railway Deployment (Recommended for Long-Term Testing)

[Railway](https://railway.app/) offers free hosting with automatic HTTPS and persistent URLs.

### Steps:

1. **Sign up**: Visit [railway.app](https://railway.app/) and sign in with GitHub

2. **Click "New Project" → "Deploy from GitHub repo"**

3. **Select this repository**

4. **Configure the deployment**:
   - Railway will auto-detect the Dockerfile
   - Set environment variables if needed
   - Port 8000 is automatically exposed

5. **Get your preview URL**:
   Railway provides a URL like: `https://your-app.railway.app`

6. **Automatic deployments**:
   - Every push to the branch triggers a new deployment
   - Preview deployments for pull requests

### Railway Features:
- ✅ Free $5/month credit (enough for small projects)
- ✅ Automatic HTTPS
- ✅ Custom domains
- ✅ Persistent URLs
- ✅ GitHub integration
- ✅ Automatic deployments

---

## Option 4: Render Deployment

[Render](https://render.com/) offers free hosting for web services.

### Steps:

1. **Sign up**: Visit [render.com](https://render.com/) and sign in with GitHub

2. **Click "New +" → "Web Service"**

3. **Connect your GitHub repository**

4. **Configure**:
   - **Name**: retraction-watch-api
   - **Environment**: Docker
   - **Plan**: Free
   - **Build Command**: (auto-detected from Dockerfile)
   - **Start Command**: (auto-detected)

5. **Deploy**: Click "Create Web Service"

6. **Get your URL**: Render provides a URL like: `https://retraction-watch-api.onrender.com`

### Render Features:
- ✅ Free tier (sleeps after inactivity)
- ✅ Automatic HTTPS
- ✅ GitHub integration
- ✅ Custom domains (paid plans)
- ⚠️ Cold start delay on free tier

---

## Option 5: Fly.io Deployment

[Fly.io](https://fly.io/) runs Docker containers globally.

### Steps:

1. **Install flyctl**:
   ```bash
   # macOS
   brew install flyctl
   
   # Linux
   curl -L https://fly.io/install.sh | sh
   ```

2. **Sign up**:
   ```bash
   fly auth signup
   ```

3. **Launch your app**:
   ```bash
   fly launch
   ```
   
   Follow the prompts:
   - Choose an app name
   - Select a region
   - Don't add a database
   - Don't deploy yet (we'll configure first)

4. **Deploy**:
   ```bash
   fly deploy
   ```

5. **Get your URL**:
   ```bash
   fly status
   ```
   Your URL: `https://your-app.fly.dev`

### Fly.io Features:
- ✅ Free tier available
- ✅ Global edge deployment
- ✅ Automatic HTTPS
- ✅ Good performance
- ✅ Simple CLI

---

## Option 6: GitHub Actions with Preview Deployment

We can set up automatic preview deployments using GitHub Actions.

See `.github/workflows/deploy-preview.yml` for the automated workflow that:
- Builds the Docker image
- Deploys to a preview environment
- Comments on PRs with the preview URL

---

## Comparison Table

| Option | Cost | Speed | Persistent URL | Auto Deploy | Best For |
|--------|------|-------|----------------|-------------|----------|
| **ngrok** | Free/Paid | ⚡ Instant | ❌ (paid: ✅) | ❌ | Quick local testing |
| **Railway** | Free $5/mo | 🚀 Fast | ✅ | ✅ | Continuous testing |
| **Render** | Free | 🐌 Slow start | ✅ | ✅ | Free hosting |
| **Fly.io** | Free | 🚀 Fast | ✅ | ✅ | Production-like |
| **Docker Compose** | Free | ⚡ Instant | Local only | ❌ | Local testing |

---

## Recommended Workflow

1. **Development**: Use `./start_api.sh` for local development
2. **Quick Testing**: Use **ngrok** to share with others
3. **PR Testing**: Use **Railway** or **Render** for preview deployments
4. **Production**: Use **Fly.io** or **Railway** with custom domain

---

## Testing Your Preview URL

Once you have a preview URL, test it:

```bash
# Set your preview URL
PREVIEW_URL="https://your-app.railway.app"

# Test endpoints
curl "$PREVIEW_URL/"
curl "$PREVIEW_URL/retractions?year=2025&page_size=5"
curl "$PREVIEW_URL/retractions/69157"
curl "$PREVIEW_URL/authors?limit=10"
curl "$PREVIEW_URL/journals?limit=10"

# Access documentation
open "$PREVIEW_URL/docs"
```

---

## Security Considerations

- 🔒 Preview URLs are public - don't use production data
- 🔒 Add rate limiting for public deployments
- 🔒 Consider adding basic authentication
- 🔒 Monitor usage and costs
- 🔒 Use environment variables for secrets

---

## Need Help?

- ngrok docs: https://ngrok.com/docs
- Railway docs: https://docs.railway.app/
- Render docs: https://render.com/docs
- Fly.io docs: https://fly.io/docs/
