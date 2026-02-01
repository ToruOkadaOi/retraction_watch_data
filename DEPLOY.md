# One-Click Deployment Buttons

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/retraction-watch-api?referralCode=bonus)

Click the button above to deploy to Railway with one click!

## Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ToruOkadaOi/retraction_watch_data)

## Deploy to Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/ToruOkadaOi/retraction_watch_data)

## Manual Deployment

For other platforms or manual deployment, see [PREVIEW_TESTING.md](PREVIEW_TESTING.md)

## Quick Preview with ngrok

For instant local preview with a public URL:

```bash
./preview_with_ngrok.sh
```

This will:
1. Start the API locally
2. Create a public ngrok URL
3. Display the URL for sharing

## Requirements

All deployment options require:
- Python 3.11+
- Docker (for containerized deployments)
- 512MB RAM minimum
- ~100MB disk space for database
