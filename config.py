"""
Configuration: topics, sources, LLM models.
"""

import json
import os
from pathlib import Path


TOPICS = {
    "world_politics": {
        "name": "World Politics & Geopolitics",
        "icon": "\U0001f30d",
    },
    "canada_politics": {
        "name": "Canadian Politics & Policy",
        "icon": "\U0001f341",
    },
    "us_politics": {
        "name": "US Politics",
        "icon": "\U0001f1fa\U0001f1f8",
    },
    "economics_business": {
        "name": "Economics & Business",
        "icon": "\U0001f4ca",
    },
    "tech_ai": {
        "name": "Technology & AI",
        "icon": "\U0001f916",
    },
    "insurance_canada": {
        "name": "Canadian Insurance Industry",
        "icon": "\U0001f6e1\ufe0f",
    },
    "data_privacy_governance": {
        "name": "Data, Privacy & AI Governance",
        "icon": "\U0001f510",
    },
    "culture_good_news": {
        "name": "Culture, Joy & Good News",
        "icon": "\U0001f308",
    },
    "climate_energy": {
        "name": "Climate & Energy",
        "icon": "\U0001f30e",
    },
    "health_science": {
        "name": "Health & Science",
        "icon": "\U0001f52c",
    },
}

# Source format: (name, url, region, bias, language)
# language: "en" for English, others for non-English (will be translated)
RSS_SOURCES = [
    # === CANADA - Mainstream ===
    ("Globe and Mail", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/news/", "Canada", "centre", "en"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-topstories", "Canada", "centre-left", "en"),
    ("National Post", "https://nationalpost.com/feed", "Canada", "centre-right", "en"),
    ("Toronto Star", "https://www.thestar.com/search/?f=rss&t=article&c=news*&l=50&s=start_time&sd=desc", "Canada", "centre-left", "en"),
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009", "Canada", "centre", "en"),
    ("Global News Canada", "https://globalnews.ca/feed/", "Canada", "centre", "en"),
    ("Macleans", "https://macleans.ca/feed/", "Canada", "centre", "en"),
    # === CANADA - Regional ===
    ("Vancouver Sun", "https://vancouversun.com/feed", "Canada-BC", "centre", "en"),
    ("Calgary Herald", "https://calgaryherald.com/feed", "Canada-AB", "centre-right", "en"),
    ("Montreal Gazette", "https://montrealgazette.com/feed", "Canada-QC", "centre", "en"),
    ("Ottawa Citizen", "https://ottawacitizen.com/feed", "Canada-ON", "centre", "en"),
    ("Winnipeg Free Press", "https://www.winnipegfreepress.com/rss", "Canada-MB", "centre", "en"),
    # === CANADA - French ===
    ("Radio-Canada", "https://ici.radio-canada.ca/rss/4159", "Canada-QC", "centre-left", "fr"),
    ("Le Devoir", "https://www.ledevoir.com/rss/manchettes.xml", "Canada-QC", "centre-left", "fr"),
    ("La Presse", "https://www.lapresse.ca/rss", "Canada-QC", "centre", "fr"),
    # === CANADA - Insurance / Industry ===
    ("Canadian Underwriter", "https://www.canadianunderwriter.ca/feed/", "Canada-Insurance", "industry", "en"),
    ("Insurance Business Canada", "https://www.insurancebusinessmag.com/ca/rss/news/", "Canada-Insurance", "industry", "en"),
    # === CANADA - Policy / Think Tanks ===
    ("C.D. Howe Institute", "https://www.cdhowe.org/rss.xml", "Canada-Policy", "centre-right", "en"),
    ("Fraser Institute", "https://www.fraserinstitute.org/rss.xml", "Canada-Policy", "right", "en"),
    ("CCPA Monitor", "https://monitormag.ca/feed/", "Canada-Policy", "left", "en"),
    # === USA - Mainstream ===
    ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "USA", "centre-left", "en"),
    ("Washington Post", "https://feeds.washingtonpost.com/rss/world", "USA", "centre-left", "en"),
    ("Wall Street Journal", "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "USA", "centre-right", "en"),
    ("AP News", "https://rsshub.app/apnews/topics/apf-topnews", "USA", "centre", "en"),
    ("Reuters", "https://www.reutersagency.com/feed/", "USA", "centre", "en"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml", "USA", "centre-left", "en"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml", "USA", "right", "en"),
    ("Politico", "https://www.politico.com/rss/politicopicks.xml", "USA", "centre", "en"),
    ("The Hill", "https://thehill.com/feed/", "USA", "centre", "en"),
    # === USA - Non-Mainstream / Ideological ===
    ("Reason", "https://reason.com/feed/", "USA", "libertarian", "en"),
    ("The Intercept", "https://theintercept.com/feed/?rss", "USA", "left", "en"),
    ("Jacobin", "https://jacobin.com/feed", "USA", "left", "en"),
    ("National Review", "https://www.nationalreview.com/feed/", "USA", "right", "en"),
    ("The American Conservative", "https://www.theamericanconservative.com/feed/", "USA", "right", "en"),
    ("The Nation", "https://www.thenation.com/feed/", "USA", "left", "en"),
    # === USA - Think Tanks ===
    ("Brookings", "https://www.brookings.edu/feed/", "USA-Policy", "centre-left", "en"),
    ("CATO Institute", "https://www.cato.org/rss/recent-opeds", "USA-Policy", "libertarian", "en"),
    ("Heritage Foundation", "https://www.heritage.org/rss/all-research", "USA-Policy", "right", "en"),
    ("Council on Foreign Relations", "https://www.cfr.org/rss.xml", "USA-Policy", "centre", "en"),
    ("Carnegie Endowment", "https://carnegieendowment.org/rss/solr.xml", "USA-Policy", "centre", "en"),
    # === UK ===
    ("BBC News", "http://feeds.bbci.co.uk/news/rss.xml", "UK", "centre", "en"),
    ("The Guardian", "https://www.theguardian.com/world/rss", "UK", "centre-left", "en"),
    ("The Telegraph", "https://www.telegraph.co.uk/rss.xml", "UK", "centre-right", "en"),
    ("Financial Times", "https://www.ft.com/rss/home", "UK", "centre", "en"),
    ("The Economist", "https://www.economist.com/international/rss.xml", "UK", "centre", "en"),
    ("The Spectator", "https://www.spectator.co.uk/feed", "UK", "right", "en"),
    # === EUROPE ===
    ("DW News", "https://rss.dw.com/rdf/rss-en-all", "Germany", "centre", "en"),
    ("France 24", "https://www.france24.com/en/rss", "France", "centre", "en"),
    ("EuroNews", "https://www.euronews.com/rss", "Europe", "centre", "en"),
    ("Politico EU", "https://www.politico.eu/feed/", "Europe", "centre", "en"),
    ("Irish Times", "https://www.irishtimes.com/cmlink/the-irish-times-news-1.1319192", "Ireland", "centre", "en"),
    # === EUROPE - Non-English editions (in English) ===
    ("Der Spiegel International", "https://www.spiegel.de/international/index.rss", "Germany", "centre-left", "en"),
    ("Le Monde Diplomatique EN", "https://mondediplo.com/backend", "France", "left", "en"),
    ("El Pais English", "https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada", "Spain", "centre-left", "en"),
    ("Corriere della Sera EN", "https://www.corriere.it/rss/english.xml", "Italy", "centre", "en"),
    # === EUROPE - Non-English (will be translated) ===
    ("Le Monde", "https://www.lemonde.fr/rss/une.xml", "France", "centre-left", "fr"),
    ("Süddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Topthemen", "Germany", "centre-left", "de"),
    ("NOS Nieuws", "https://feeds.nos.nl/nosnieuwsalgemeen", "Netherlands", "centre", "nl"),
    # === MIDDLE EAST ===
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Qatar/ME", "centre", "en"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/", "Israel", "centre", "en"),
    ("Arab News", "https://www.arabnews.com/rss.xml", "Saudi Arabia", "centre", "en"),
    ("Middle East Eye", "https://www.middleeasteye.net/rss", "UK/ME", "centre", "en"),
    ("The New Arab", "https://www.newarab.com/rss", "UK/ME", "centre-left", "en"),
    ("Haaretz", "https://www.haaretz.com/cmlink/1.628765", "Israel", "centre-left", "en"),
    ("Iran International", "https://www.iranintl.com/en/feed", "UK/Iran", "centre", "en"),
    ("Daily Sabah", "https://www.dailysabah.com/rssFeed/", "Turkey", "centre-right", "en"),
    # === ASIA-PACIFIC ===
    ("South China Morning Post", "https://www.scmp.com/rss/91/feed", "Hong Kong", "centre", "en"),
    ("NHK World", "https://www3.nhk.or.jp/rss/news/cat0.xml", "Japan", "centre", "en"),
    ("The Straits Times", "https://www.straitstimes.com/news/world/rss.xml", "Singapore", "centre", "en"),
    ("ABC Australia", "https://www.abc.net.au/news/feed/2942460/rss.xml", "Australia", "centre", "en"),
    ("India Today", "https://www.indiatoday.in/rss/home", "India", "centre", "en"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss", "Japan", "centre", "en"),
    ("The Wire India", "https://thewire.in/feed", "India", "centre-left", "en"),
    ("Rappler", "https://www.rappler.com/feed/", "Philippines", "centre", "en"),
    ("Jakarta Post", "https://www.thejakartapost.com/rss", "Indonesia", "centre", "en"),
    ("Channel News Asia", "https://www.channelnewsasia.com/rss", "Singapore", "centre", "en"),
    ("Taipei Times", "https://www.taipeitimes.com/xml/index.rss", "Taiwan", "centre", "en"),
    ("The Hindu", "https://www.thehindu.com/feeder/default.rss", "India", "centre-left", "en"),
    ("Yonhap News", "https://en.yna.co.kr/RSS/news.xml", "South Korea", "centre", "en"),
    ("Bangkok Post", "https://www.bangkokpost.com/rss/data/topstories.xml", "Thailand", "centre", "en"),
    # === ASIA - Non-English (key sources, will be translated) ===
    ("Yomiuri Shimbun", "https://www.yomiuri.co.jp/feed/", "Japan", "centre-right", "ja"),
    ("Dong-A Ilbo", "https://www.donga.com/news/rss/RSS.xml", "South Korea", "centre", "ko"),
    # === AFRICA ===
    ("Al Monitor", "https://www.al-monitor.com/rss", "Middle East/Africa", "centre", "en"),
    ("The East African", "https://www.theeastafrican.co.ke/tea/rss", "East Africa", "centre", "en"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/dmrss/", "South Africa", "centre-left", "en"),
    ("Mail & Guardian", "https://mg.co.za/feed/", "South Africa", "centre-left", "en"),
    ("Punch Nigeria", "https://punchng.com/feed/", "Nigeria", "centre", "en"),
    ("The Citizen Tanzania", "https://www.thecitizen.co.tz/rss", "Tanzania", "centre", "en"),
    ("Nation Africa", "https://nation.africa/rss", "Kenya", "centre", "en"),
    # === LATIN AMERICA ===
    ("Buenos Aires Herald", "https://buenosairesherald.com/feed/", "Argentina", "centre", "en"),
    ("Mexico News Daily", "https://mexiconewsdaily.com/feed/", "Mexico", "centre", "en"),
    ("Brazil Wire", "https://www.brasilwire.com/feed/", "Brazil", "left", "en"),
    ("Merco Press", "https://en.mercopress.com/rss", "Latin America", "centre", "en"),
    ("Agencia Brasil EN", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "Brazil", "centre", "en"),
    # === FAITH / VALUES ===
    ("Vatican News", "https://www.vaticannews.va/en.rss.xml", "Vatican", "religious", "en"),
    ("Christianity Today", "https://www.christianitytoday.com/feed/", "USA", "religious-right", "en"),
    ("Religion News Service", "https://religionnews.com/feed/", "USA", "centre", "en"),
    # === LABOR / WORKER ===
    ("Labor Notes", "https://labornotes.org/rss.xml", "USA-Labor", "left", "en"),
    ("In These Times", "https://inthesetimes.com/feed", "USA-Labor", "left", "en"),
    # === TECH / AI ===
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "USA-Tech", "centre", "en"),
    ("TechCrunch", "https://techcrunch.com/feed/", "USA-Tech", "centre", "en"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "USA-Tech", "centre", "en"),
    ("Wired", "https://www.wired.com/feed/rss", "USA-Tech", "centre", "en"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "USA-Tech", "centre", "en"),
    ("VentureBeat", "https://venturebeat.com/feed/", "USA-Tech", "centre", "en"),
    ("The Register", "https://www.theregister.com/headlines.atom", "UK-Tech", "centre", "en"),
    ("Hacker News (top)", "https://hnrss.org/frontpage", "USA-Tech", "centre", "en"),
    # === AI SPECIFIC ===
    ("AI News", "https://www.artificialintelligence-news.com/feed/", "Global-AI", "centre", "en"),
    ("The Decoder", "https://the-decoder.com/feed/", "Global-AI", "centre", "en"),
    ("Jack Clark Import AI", "https://importai.substack.com/feed", "Global-AI", "centre", "en"),
    # === DATA / PRIVACY / GOVERNANCE ===
    ("IAPP", "https://iapp.org/news/feed/", "Global-Privacy", "centre", "en"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "USA-Security", "centre", "en"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "USA-Security", "centre", "en"),
    ("The Record", "https://therecord.media/feed", "USA-Security", "centre", "en"),
    ("Schneier on Security", "https://www.schneier.com/feed/", "USA-Security", "centre", "en"),
    ("Lawfare", "https://www.lawfaremedia.org/rss.xml", "USA-Legal", "centre", "en"),
    ("Tech Policy Press", "https://www.techpolicy.press/feed/", "USA-Policy", "centre", "en"),
    # === ECONOMICS / BUSINESS ===
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "USA-Finance", "centre", "en"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "USA-Finance", "centre", "en"),
    ("MarketWatch", "https://www.marketwatch.com/rss/topstories", "USA-Finance", "centre", "en"),
    ("BNN Bloomberg Canada", "https://www.bnnbloomberg.ca/arc/outboundfeeds/rss/category/news/?outputType=xml", "Canada-Finance", "centre", "en"),
    # === GOOD NEWS / CULTURE ===
    ("Positive News", "https://www.positive.news/feed/", "UK-Culture", "centre", "en"),
    ("Good News Network", "https://www.goodnewsnetwork.org/feed/", "USA-Culture", "centre", "en"),
    ("Reasons to be Cheerful", "https://reasonstobecheerful.world/feed/", "USA-Culture", "centre", "en"),
    ("Atlas Obscura", "https://www.atlasobscura.com/feeds/latest", "USA-Culture", "centre", "en"),
    ("Aeon", "https://aeon.co/feed.rss", "Global-Culture", "centre", "en"),
    # === CLIMATE / ENERGY ===
    ("Carbon Brief", "https://www.carbonbrief.org/feed", "UK-Climate", "centre", "en"),
    ("CleanTechnica", "https://cleantechnica.com/feed/", "USA-Climate", "centre-left", "en"),
    ("Energy Monitor", "https://www.energymonitor.ai/feed/", "UK-Climate", "centre", "en"),
    # === HEALTH / SCIENCE ===
    ("STAT News", "https://www.statnews.com/feed/", "USA-Health", "centre", "en"),
    ("Nature News", "https://www.nature.com/nature.rss", "UK-Science", "centre", "en"),
    ("New Scientist", "https://www.newscientist.com/feed/home/", "UK-Science", "centre", "en"),
]

LLM_CONFIGS = {
    "gemini": {
        "provider": "google", "model": "gemini-2.5-flash",
        "env_key": "GOOGLE_API_KEY", "label": "Gemini Flash",
        "tier": "cheap",  # for routing decisions
    },
    "gemini_pro": {
        "provider": "google", "model": "gemini-2.5-pro",
        "env_key": "GOOGLE_API_KEY", "label": "Gemini Pro",
        "tier": "quality",
    },
    "chatgpt": {
        "provider": "openai", "model": "gpt-4.1",
        "env_key": "OPENAI_API_KEY", "label": "ChatGPT",
        "tier": "quality",
    },
    "claude": {
        "provider": "anthropic", "model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY", "label": "Claude",
        "tier": "quality",
    },
    "grok": {
        "provider": "xai", "model": "grok-3-fast",
        "env_key": "XAI_API_KEY", "label": "Grok",
        "tier": "cheap",
    },
}


# Materiality threshold: stories with avg importance below this are dropped
MATERIALITY_CUTOFF = 3.5  # on 1-10 scale

# Max stories (safety valve, not the primary cutoff)
MAX_STORIES = 20

# Depth tier thresholds (based on 1-5 star importance)
DEPTH_THRESHOLDS = {
    "deep": 4,      # 4-5 stars: full investigation
    "standard": 3,  # 3 stars: compare + write
    "brief": 0,     # 1-2 stars: summary only
}


def load_query_pack(path):
    if not path or not Path(path).exists():
        return None
    with open(path) as f:
        return json.load(f)


def get_active_sources(pack=None):
    if pack and "sources" in pack and pack["sources"] != "all":
        allowed = set(pack["sources"])
        return [s for s in RSS_SOURCES if s[0] in allowed]
    return RSS_SOURCES


def get_active_topics(pack=None):
    if pack and "topics" in pack:
        allowed = set(pack["topics"])
        return {k: v for k, v in TOPICS.items() if k in allowed}
    return TOPICS
