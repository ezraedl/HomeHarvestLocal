# Trigger Scraper Rebuild After HomeHarvestLocal Changes

This workflow automatically triggers a rebuild of the `real-estate-crm-scraper` service when changes are pushed to HomeHarvestLocal.

## Setup Instructions

### Method 1: Railway API (Current Implementation)

1. **Get Railway Token:**
   - Go to Railway dashboard: https://railway.app/account/tokens
   - Create a new token with deployment permissions
   - Copy the token

2. **Get Railway Service ID:**
   - Go to your scraper service in Railway dashboard
   - Check the service settings or use Railway CLI: `railway service`
   - The service ID is in the URL or settings

3. **Add GitHub Secrets:**
   - Go to your HomeHarvestLocal GitHub repository
   - Navigate to: Settings → Secrets and variables → Actions
   - Add the following secrets:
     - `RAILWAY_TOKEN`: Your Railway API token
     - `RAILWAY_SERVICE_ID`: Your scraper service ID

4. **Test the workflow:**
   - Push a change to the `master` or `main` branch
   - Check the Actions tab to see if the workflow runs
   - Check Railway dashboard to verify a new deployment was triggered

### Method 2: Railway Webhook (Alternative)

If the API method doesn't work, you can use Railway webhooks:

1. **Create Railway Webhook:**
   - In Railway dashboard, go to your scraper service
   - Navigate to Settings → Webhooks
   - Create a new webhook
   - Copy the webhook URL

2. **Update the workflow:**
   - Replace the Railway API call with a simple webhook POST:
   ```yaml
   curl -X POST "${{ secrets.RAILWAY_WEBHOOK_URL }}"
   ```

3. **Add GitHub Secret:**
   - Add `RAILWAY_WEBHOOK_URL` to your GitHub repository secrets

### Method 3: Manual Trigger (Simplest)

If you prefer manual control, you can:
- Go to Railway dashboard → Your scraper service → Deployments → Redeploy
- Or use Railway CLI: `railway up` in the scraper directory

## How It Works

When you push changes to HomeHarvestLocal:
1. GitHub Actions workflow triggers
2. It calls Railway API/webhook to start a new deployment
3. Railway rebuilds the scraper (which reinstalls dependencies including the updated HomeHarvestLocal)
4. The scraper picks up the latest HomeHarvestLocal changes

## Notes

- Railway automatically detects git dependency changes when rebuilding
- Since you're using `git+https://github.com/ezraedl/HomeHarvestLocal.git@master`, Railway will fetch the latest commit from master branch
- The rebuild ensures the scraper uses the updated HomeHarvestLocal code

