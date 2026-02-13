# 🌐 Global Briefing

An AI-powered news intelligence system that pulls from 70+ diverse global sources, identifies the most important stories, gathers multiple perspectives, and uses multiple LLMs to analyze and synthesize everything into a clean daily briefing.

## What It Does

1. **Pulls from 70+ RSS feeds** across the globe (Canada, USA, UK, Europe, Middle East, Asia-Pacific, Africa, Latin America)
2. **Triages articles** by your topics of interest using fast keyword matching + optional Gemini Flash refinement
3. **Detects multi-perspective stories** — when the same event is covered by different outlets, it groups them to show you contrasting coverage
4. **Sends top stories to multiple LLMs** (Gemini, ChatGPT, Claude, Grok) for diverse analytical perspectives
5. **Synthesizes everything** into a concise executive briefing
6. **Publishes to a beautiful, mobile-friendly website** (hosted free on GitHub Pages)

## Your Topics

- 🌍 World Politics & Geopolitics
- 🍁 Canadian Politics & Policy
- 🇺🇸 US Politics
- 📊 Economics & Business
- 🤖 Technology & AI
- 🛡️ Canadian Insurance Industry
- 🔐 Data, Privacy & AI Governance (including breaches, political commentary, regulation)
- 🌈 Culture, Joy & Good News

## Cost

- **Hosting**: Free (GitHub Actions + GitHub Pages)
- **LLM API calls**: ~$5-12/month depending on how many LLMs you enable
- **Total**: Well under $15/month

### Cost Breakdown

| Component | Cost |
|-----------|------|
| GitHub Actions (2 runs/day) | Free (within free tier) |
| GitHub Pages hosting | Free |
| Gemini Flash triage (~50 articles/run) | ~$0.01/day |
| Multi-LLM analysis (~20 stories × 4 LLMs × 2/day) | ~$0.25-0.40/day |
| Synthesis call | ~$0.01/day |
| **Monthly total** | **~$8-12** |

## Quick Setup (15 minutes)

### 1. Create the Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it `global-briefing` (or whatever you like)
3. Make it **private** (your API keys will be in secrets, but still)
4. Upload all the files from this project

### 2. Add Your API Keys

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add whichever of these you have (you need at least ONE, but more = more perspectives):

| Secret Name | Where to Get It |
|-------------|----------------|
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) (free tier available!) |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| `XAI_API_KEY` | [console.x.ai](https://console.x.ai/) |

**Budget tip**: Start with just `GOOGLE_API_KEY` (Gemini has a generous free tier). Add others as you want more perspectives.

### 3. Enable GitHub Pages

1. Go to repo → **Settings** → **Pages**
2. Under "Source", select **GitHub Actions**
3. Save

### 4. Run It!

1. Go to repo → **Actions** tab
2. Click "Global Briefing" workflow
3. Click **"Run workflow"** → **"Run workflow"**
4. Wait ~3-5 minutes
5. Visit `https://YOUR-USERNAME.github.io/global-briefing/`

It will now run automatically at 6:00 AM and 5:00 PM Eastern every day.

## Customization

### Change Run Times

Edit `.github/workflows/briefing.yml` and modify the cron schedules:

```yaml
schedule:
  - cron: '0 11 * * *'   # 6 AM Eastern (11 UTC)
  - cron: '0 22 * * *'   # 5 PM Eastern (22 UTC)
```

### Add/Remove Sources

Edit the `RSS_SOURCES` list in `briefing.py`. Each source is a tuple:
```python
("Source Name", "https://feed-url.com/rss", "Region", "bias-label")
```

The bias label is just for your reference — it helps when viewing multi-perspective stories.

### Adjust Topics

Edit the `TOPICS` dictionary in `briefing.py`. Each topic has keywords that the triage system uses:
```python
"your_topic": {
    "name": "Display Name",
    "icon": "🎯",
    "keywords": ["keyword1", "keyword2", ...],
}
```

### Change LLM Models

Edit the `LLM_CONFIGS` dictionary to use different models (e.g., switch to `gpt-4o` for deeper analysis, or `gemini-1.5-flash` for cheaper triage).

## Architecture

```
RSS Feeds (70+)
    │
    ▼
[Fetch Layer] — parallel, fault-tolerant, per-feed error handling
    │
    ▼
[Keyword Triage] — FREE, local, fast topic classification
    │
    ▼
[Story Grouping] — title similarity to detect same-story coverage
    │
    ▼
[LLM Triage] — Gemini Flash picks the top 15-20 (costs pennies)
    │
    ▼
[Multi-LLM Analysis] — each story analyzed by available LLMs
    │
    ▼
[Synthesis] — one LLM weaves it all together
    │
    ▼
[HTML Generation] — mobile-friendly briefing page
    │
    ▼
[GitHub Pages] — free hosting, accessible anywhere
```

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys (at least one)
export GOOGLE_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"      # optional
export ANTHROPIC_API_KEY="your-key-here"   # optional
export XAI_API_KEY="your-key-here"         # optional

# Run
python briefing.py

# Open output/index.html in your browser
```

## Troubleshooting

**"No articles fetched"**
- Check your internet connection
- Some corporate networks block RSS feeds
- Try running locally first

**Only some LLMs responding**
- Check that your API keys are correctly set in GitHub Secrets
- Verify keys haven't expired
- Check your API credit balances

**GitHub Actions not running**
- Make sure Actions are enabled in your repo settings
- Check the Actions tab for error logs
- The free tier allows ~2000 minutes/month; this uses ~10 min/day

## Future Enhancements

- [ ] Email delivery option (via SendGrid/Mailgun free tier)
- [ ] Historical archive page
- [ ] RSS output (briefing-of-briefings)
- [ ] Sentiment tracking over time
- [ ] Custom source confidence scoring
- [ ] Translation layer for non-English sources
