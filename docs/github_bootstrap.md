# GitHub Bootstrap

## 1. Create private repo
Name: `dalal-street-engine`. Private. Do NOT initialize with README.

## 2. Push code
```bash
git init -b main
git add .
git commit -m "v6.4 Week 1"
git remote add origin https://github.com/<you>/dalal-street-engine.git
git push -u origin main
```

## 3. Add secrets
Settings → Secrets and variables → Actions → New repository secret:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

## 4. Verify workflows
Actions tab → should show 4 workflows. Trigger EOD Pipeline manually.
