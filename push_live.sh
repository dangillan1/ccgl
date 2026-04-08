#!/bin/bash
# CCGL — regenerate report and push live to GitHub Pages
# Usage: ./push_live.sh
# Or add to cron/scheduled task for auto-push after hourly report runs

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

echo "🌿 CCGL Push Live"
echo "─────────────────"

# 1. Clean any stale git lock files
echo "Cleaning stale git locks..."
find .git -name "*.lock" -delete 2>/dev/null
find .git/objects -name "tmp_obj_*" -delete 2>/dev/null

# 2. Fetch live GrowLink data (requires data/config.json with bearer token)
echo "Fetching live GrowLink data..."
python3 fetch_growlink.py
FETCH_RC=$?
if [ $FETCH_RC -eq 2 ]; then
    echo "⚠ GrowLink auth failed (token expired) — continuing with existing data"
elif [ $FETCH_RC -ne 0 ]; then
    echo "⚠ GrowLink fetch failed (rc=$FETCH_RC) — continuing with existing data"
fi

# 3. Build daily summaries from hourly readings (keeps 24h data current)
echo "Building daily summaries..."
python3 build_daily_summaries.py
if [ $? -ne 0 ]; then
    echo "⚠ Daily summary build failed — continuing anyway"
fi

# 3. Regenerate report with latest data
echo "Regenerating report..."
python3 generate_report.py
if [ $? -ne 0 ]; then
    echo "❌ Report generation failed — aborting push"
    exit 1
fi

# 4. Pull latest remote changes (merge strategy: keep ours for generated files)
echo "Syncing with remote..."
git pull origin main --no-rebase --strategy-option=ours -q 2>/dev/null || true
find .git -name "*.lock" -delete 2>/dev/null

# 5. Stage and commit
echo "Staging changes..."
git add index.html CCGL-Hourly-Report-Latest.html generate_report.py generate_email.py build_daily_summaries.py fetch_growlink.py report_template.html data/events.json data/daily-summaries.json data/state.json data/hourly-readings.json logo.png wordmark.png push_live.sh .gitignore 2>/dev/null

# Only commit if there are staged changes
if git diff --cached --quiet; then
    echo "✓ Nothing new to commit — already up to date"
else
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
    git commit -m "Hourly report update $TIMESTAMP" -q
    echo "✓ Committed"
fi

# 6. Push
echo "Pushing to GitHub Pages..."
git push origin main
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Live at https://dangillan1.github.io/ccgl/"
else
    echo "❌ Push failed — check your connection or auth"
fi
