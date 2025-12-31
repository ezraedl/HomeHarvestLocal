# Auto-Deploy Setup: HomeHarvestLocal → Scraper

This workflow automatically triggers a Railway deployment of the scraper service whenever HomeHarvestLocal is updated.

## Setup Instructions

### 1. Get Railway Credentials

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Select your scraper project
3. Go to **Settings** → **API Tokens**
4. Create a new API token and copy it

5. Get your Project ID and Service ID:
   - **Project ID**: Found in the project URL: `railway.app/project/{PROJECT_ID}`
   - **Service ID**: Found in service settings or API responses

### 2. Configure GitHub Secrets

In the **HomeHarvestLocal** repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:

   - `RAILWAY_API_TOKEN`: Your Railway API token
   - `RAILWAY_PROJECT_ID`: Your Railway project ID
   - `RAILWAY_SERVICE_ID`: Your Railway service ID (for the scraper service)
   - `SCRAPER_REPO_TOKEN` (optional, fallback method): A GitHub Personal Access Token with repo permissions for the scraper repository

### 3. How It Works

When you push to the `master` or `main` branch of HomeHarvestLocal with changes to:
- `homeharvest/**` files
- `pyproject.toml`

The workflow will:
1. Use Railway API to trigger a new deployment of the scraper service
2. If API method fails, fallback to creating an empty commit in the scraper repo (requires `SCRAPER_REPO_TOKEN`)

### 4. Verify It's Working

1. Make a change to `homeharvest/core/scrapers/__init__.py`
2. Commit and push to `master`
3. Check the Actions tab in HomeHarvestLocal repo - you should see "Trigger Scraper Deployment" running
4. Check Railway dashboard - you should see a new deployment triggered

### 5. Troubleshooting

**Workflow not triggering:**
- Check that you're pushing to `master` or `main` branch
- Verify the changed files match the paths filter

**Railway deployment not starting:**
- Verify all three Railway secrets are set correctly
- Check Railway API token has deployment permissions
- Verify Service ID is correct

**Fallback method not working:**
- Ensure `SCRAPER_REPO_TOKEN` is set
- Token needs `repo` scope
- Verify Railway is watching the scraper repo for pushes

