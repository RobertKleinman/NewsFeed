"""
Configuration: topics, sources, LLM models.
For query packs, the runner loads a JSON config that can override
which sources and topics are active.
"""

import json
import os
from pathlib import Path


TOPICS = {
    "world_politics": {
        "name": "World Politics & Geopolitics",
        "icon": "\U0001f30d",
        "keywords": ["geopolitics", "diplomacy", "war", "conflict", "UN", "NATO", "sanctions",
                      "treaty", "summit", "foreign policy", "military", "peace", "election",
                      "coup", "protest", "refugee", "international", "alliance"],
    },
    "canada_politics": {
        "name": "Canadian Politics & Policy",
        "icon": "\U0001f341",
        "keywords": ["canada", "canadian", "ottawa", "trudeau", "poilievre", "parliament",
                      "liberal", "conservative", "ndp", "bloc", "senate", "provincial",
                      "ontario", "quebec", "british columbia", "alberta", "federal"],
    },
    "us_politics": {
        "name": "US Politics",
        "icon": "\U0001f1fa\U0001f1f8",
        "keywords": ["congress", "senate", "white house", "supreme court", "democrat",
                      "republican", "washington", "biden", "trump", "election", "governor",
                      "legislation", "executive order", "pentagon", "state department"],
    },
    "economics_business": {
        "name": "Economics & Business",
        "icon": "\U0001f4ca",
        "keywords": ["economy", "gdp", "inflation", "interest rate", "central bank",
                      "stock", "market", "trade", "tariff", "recession", "employment",
                      "startup", "merger", "acquisition", "ipo", "venture", "earnings",
                      "supply chain", "manufacturing", "banking"],
    },
    "tech_ai": {
        "name": "Technology & AI",
        "icon": "\U0001f916",
        "keywords": ["artificial intelligence", "machine learning", "AI", "LLM", "chatgpt",
                      "openai", "anthropic", "google deepmind", "meta ai", "robot",
                      "automation", "semiconductor", "chip", "quantum", "software",
                      "cloud", "cybersecurity", "startup", "tech company", "silicon valley"],
    },
    "insurance_canada": {
        "name": "Canadian Insurance Industry",
        "icon": "\U0001f6e1\ufe0f",
        "keywords": ["insurance", "insurer", "underwriting", "claims", "actuarial",
                      "reinsurance", "broker", "premium", "FSRA", "OSFI", "IBC",
                      "auto insurance", "property casualty", "P&C", "insurance regulation",
                      "insurance canada", "facility association"],
    },
    "data_privacy_governance": {
        "name": "Data, Privacy & AI Governance",
        "icon": "\U0001f510",
        "keywords": ["data breach", "privacy", "GDPR", "PIPEDA", "data protection",
                      "surveillance", "facial recognition", "biometric", "consent",
                      "data governance", "AI regulation", "AI ethics", "AI safety",
                      "algorithmic", "transparency", "accountability", "CPPA",
                      "Bill C-27", "digital charter", "cookie", "tracking", "personal data",
                      "data commissioner", "information commissioner"],
    },
    "culture_good_news": {
        "name": "Culture, Joy & Good News",
        "icon": "\U0001f308",
        "keywords": ["breakthrough", "discovery", "achievement", "celebration", "art",
                      "music", "film", "book", "festival", "award", "charity",
                      "volunteer", "community", "heartwarming", "inspiring", "milestone",
                      "culture", "museum", "theatre", "theater", "concert", "exhibition"],
    },
}

RSS_SOURCES = [
    # === CANADA - Mainstream ===
    ("Globe and Mail", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/news/", "Canada", "centre"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-topstories", "Canada", "centre-left"),
    ("National Post", "https://nationalpost.com/feed", "Canada", "centre-right"),
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=news*&l=50&s=start_time&sd=desc", "Canada", "centre-left"),
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009", "Canada", "centre"),
    ("Global News Canada", "https://globalnews.ca/feed/", "Canada", "centre"),
    ("Macleans", "https://macleans.ca/feed/", "Canada", "centre"),
    # === CANADA - Regional ===
    ("Vancouver Sun", "https://vancouversun.com/feed", "Canada-BC", "centre"),
    ("Calgary Herald", "https://calgaryherald.com/feed", "Canada-AB", "centre-right"),
    ("Montreal Gazette", "https://montrealgazette.com/feed", "Canada-QC", "centre"),
    ("Ottawa Citizen", "https://ottawacitizen.com/feed", "Canada-ON", "centre"),
    ("Winnipeg Free Press", "https://www.winnipegfreepress.com/rss", "Canada-MB", "centre"),
    # === CANADA - Insurance / Industry ===
    ("Canadian Underwriter", "https://www.canadianunderwriter.ca/feed/", "Canada-Insurance", "industry"),
    ("Insurance Business Canada", "https://www.insurancebusinessmag.com/ca/rss/news/", "Canada-Insurance", "industry"),
    # === CANADA - Policy / Think Tanks ===
    ("C.D. Howe Institute", "https://www.cdhowe.org/rss.xml", "Canada-Policy", "centre-right"),
    ("Fraser Institute", "https://www.fraserinstitute.org/rss.xml", "Canada-Policy", "right"),
    ("CCPA Monitor", "https://monitormag.ca/feed/", "Canada-Policy", "left"),
    # === USA - Mainstream ===
    ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "USA", "centre-left"),
    ("Washington Post", "https://feeds.washingtonpost.com/rss/world", "USA", "centre-left"),
    ("Wall Street Journal", "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "USA", "centre-right"),
    ("AP News", "https://rsshub.app/apnews/topics/apf-topnews", "USA", "centre"),
    ("Reuters", "https://www.reutersagency.com/feed/", "USA", "centre"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml", "USA", "centre-left"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml", "USA", "right"),
    ("Politico", "https://www.politico.com/rss/politicopicks.xml", "USA", "centre"),
    ("The Hill", "https://thehill.com/feed/", "USA", "centre"),
    # === USA - Non-Mainstream / Ideological ===
    ("Reason", "https://reason.com/feed/", "USA", "libertarian"),
    ("The Intercept", "https://theintercept.com/feed/?rss", "USA", "left"),
    ("Jacobin", "https://jacobin.com/feed", "USA", "left"),
    ("National Review", "https://www.nationalreview.com/feed/", "USA", "right"),
    ("The American Conservative", "https://www.theamericanconservative.com/feed/", "USA", "right"),
    ("The Nation", "https://www.thenation.com/feed/", "USA", "left"),
    # === USA - Think Tanks ===
    ("Brookings", "https://www.brookings.edu/feed/", "USA-Policy", "centre-left"),
    ("CATO Institute", "https://www.cato.org/rss/recent-opeds", "USA-Policy", "libertarian"),
    ("Heritage Foundation", "https://www.heritage.org/rss/all-research", "USA-Policy", "right"),
    ("Council on Foreign Relations", "https://www.cfr.org/rss.xml", "USA-Policy", "centre"),
    ("Carnegie Endowment", "https://carnegieendowment.org/rss/solr.xml", "USA-Policy", "centre"),
    # === UK ===
    ("BBC News", "http://feeds.bbci.co.uk/news/rss.xml", "UK", "centre"),
    ("The Guardian", "https://www.theguardian.com/world/rss", "UK", "centre-left"),
    ("The Telegraph", "https://www.telegraph.co.uk/rss.xml", "UK", "centre-right"),
    ("Financial Times", "https://www.ft.com/rss/home", "UK", "centre"),
    ("The Economist", "https://www.economist.com/international/rss.xml", "UK", "centre"),
    ("The Spectator", "https://www.spectator.co.uk/feed", "UK", "right"),
    # === EUROPE ===
    ("DW News", "https://rss.dw.com/rdf/rss-en-all", "Germany", "centre"),
    ("France 24", "https://www.france24.com/en/rss", "France", "centre"),
    ("EuroNews", "https://www.euronews.com/rss", "Europe", "centre"),
    ("The Local EU", "https://www.thelocal.com/feeds/rss.php", "Europe", "centre"),
    ("Politico EU", "https://www.politico.eu/feed/", "Europe", "centre"),
    ("Irish Times", "https://www.irishtimes.com/cmlink/the-irish-times-news-1.1319192", "Ireland", "centre"),
    # === MIDDLE EAST ===
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Qatar/ME", "centre"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/", "Israel", "centre"),
    ("Arab News", "https://www.arabnews.com/rss.xml", "Saudi Arabia", "centre"),
    ("Middle East Eye", "https://www.middleeasteye.net/rss", "UK/ME", "centre"),
    ("The New Arab", "https://www.newarab.com/rss", "UK/ME", "centre-left"),
    # === ASIA-PACIFIC ===
    ("South China Morning Post", "https://www.scmp.com/rss/91/feed", "Hong Kong", "centre"),
    ("NHK World", "https://www3.nhk.or.jp/rss/news/cat0.xml", "Japan", "centre"),
    ("The Straits Times", "https://www.straitstimes.com/news/world/rss.xml", "Singapore", "centre"),
    ("ABC Australia", "https://www.abc.net.au/news/feed/2942460/rss.xml", "Australia", "centre"),
    ("India Today", "https://www.indiatoday.in/rss/home", "India", "centre"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss", "Japan", "centre"),
    ("The Wire India", "https://thewire.in/feed", "India", "centre-left"),
    ("Rappler", "https://www.rappler.com/feed/", "Philippines", "centre"),
    ("Jakarta Post", "https://www.thejakartapost.com/rss", "Indonesia", "centre"),
    ("Channel News Asia", "https://www.channelnewsasia.com/rss", "Singapore", "centre"),
    ("Taipei Times", "https://www.taipeitimes.com/xml/index.rss", "Taiwan", "centre"),
    # === AFRICA ===
    ("Al Monitor", "https://www.al-monitor.com/rss", "Middle East/Africa", "centre"),
    ("The East African", "https://www.theeastafrican.co.ke/tea/rss", "East Africa", "centre"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/dmrss/", "South Africa", "centre-left"),
    ("Mail & Guardian", "https://mg.co.za/feed/", "South Africa", "centre-left"),
    ("Punch Nigeria", "https://punchng.com/feed/", "Nigeria", "centre"),
    # === LATIN AMERICA ===
    ("Buenos Aires Herald", "https://buenosairesherald.com/feed/", "Argentina", "centre"),
    ("Mexico News Daily", "https://mexiconewsdaily.com/feed/", "Mexico", "centre"),
    ("Brazil Wire", "https://www.brasilwire.com/feed/", "Brazil", "left"),
    # === FAITH / VALUES ===
    ("Vatican News", "https://www.vaticannews.va/en.rss.xml", "Vatican", "religious"),
    ("Christianity Today", "https://www.christianitytoday.com/feed/", "USA", "religious-right"),
    ("Religion News Service", "https://religionnews.com/feed/", "USA", "centre"),
    # === LABOR / WORKER ===
    ("Labor Notes", "https://labornotes.org/rss.xml", "USA-Labor", "left"),
    ("In These Times", "https://inthesetimes.com/feed", "USA-Labor", "left"),
    # === TECH / AI ===
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "USA-Tech", "centre"),
    ("TechCrunch", "https://techcrunch.com/feed/", "USA-Tech", "centre"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "USA-Tech", "centre"),
    ("Wired", "https://www.wired.com/feed/rss", "USA-Tech", "centre"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "USA-Tech", "centre"),
    ("VentureBeat", "https://venturebeat.com/feed/", "USA-Tech", "centre"),
    ("The Register", "https://www.theregister.com/headlines.atom", "UK-Tech", "centre"),
    ("Hacker News (top)", "https://hnrss.org/frontpage", "USA-Tech", "centre"),
    # === AI SPECIFIC ===
    ("AI News", "https://www.artificialintelligence-news.com/feed/", "Global-AI", "centre"),
    ("The Decoder", "https://the-decoder.com/feed/", "Global-AI", "centre"),
    ("Jack Clark Import AI", "https://importai.substack.com/feed", "Global-AI", "centre"),
    # === DATA / PRIVACY / GOVERNANCE ===
    ("IAPP", "https://iapp.org/news/feed/", "Global-Privacy", "centre"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "USA-Security", "centre"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "USA-Security", "centre"),
    ("The Record", "https://therecord.media/feed", "USA-Security", "centre"),
    ("Schneier on Security", "https://www.schneier.com/feed/", "USA-Security", "centre"),
    ("Lawfare", "https://www.lawfaremedia.org/rss.xml", "USA-Legal", "centre"),
    ("Tech Policy Press", "https://www.techpolicy.press/feed/", "USA-Policy", "centre"),
    # === ECONOMICS / BUSINESS ===
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "USA-Finance", "centre"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "USA-Finance", "centre"),
    ("MarketWatch", "https://www.marketwatch.com/rss/topstories", "USA-Finance", "centre"),
    ("BNN Bloomberg Canada", "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/category/news/?outputType=xml", "Canada-Finance", "centre"),
    # === GOOD NEWS / CULTURE ===
    ("Positive News", "https://www.positive.news/feed/", "UK-Culture", "centre"),
    ("Good News Network", "https://www.goodnewsnetwork.org/feed/", "USA-Culture", "centre"),
    ("Reasons to be Cheerful", "https://reasonstobecheerful.world/feed/", "USA-Culture", "centre"),
    ("Atlas Obscura", "https://www.atlasobscura.com/feeds/latest", "USA-Culture", "centre"),
    ("Aeon", "https://aeon.co/feed.rss", "Global-Culture", "centre"),
]

LLM_CONFIGS = {
    "gemini": {
        "provider": "google", "model": "gemini-3-flash-preview",
        "env_key": "GOOGLE_API_KEY", "label": "Gemini",
    },
    "chatgpt": {
        "provider": "openai", "model": "gpt-4.1",
        "env_key": "OPENAI_API_KEY", "label": "ChatGPT",
    },
    "claude": {
        "provider": "anthropic", "model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY", "label": "Claude",
    },
    "grok": {
        "provider": "xai", "model": "grok-3-fast",
        "env_key": "XAI_API_KEY", "label": "Grok",
    },
}


def load_query_pack(path):
    """Load a JSON config pack that overrides default sources/topics."""
    if not path or not Path(path).exists():
        return None
    with open(path) as f:
        return json.load(f)


def get_active_sources(pack=None):
    """Return sources list, optionally filtered by a query pack."""
    if pack and "sources" in pack and pack["sources"] != "all":
        allowed = set(pack["sources"])
        return [s for s in RSS_SOURCES if s[0] in allowed]
    return RSS_SOURCES


def get_active_topics(pack=None):
    """Return topics dict, optionally filtered by a query pack."""
    if pack and "topics" in pack:
        allowed = set(pack["topics"])
        return {k: v for k, v in TOPICS.items() if k in allowed}
    return TOPICS
