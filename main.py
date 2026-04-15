import os
import json
import re
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.mount("/static", StaticFiles(directory="static"), name="static")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── DOMAIN MAPPING ───────────────────────────────────────────────────────────
# Maps: source domain → { lang: target domain }
# Add more satellite site groups here as needed.

DOMAIN_GROUPS = [
    {
        "sl": "www.maaarket.si",
        "hr": "www.maaarket.hr",
        "rs": "www.maaarket.rs",
        "hu": "www.maaarket.hu",
        "cz": "www.maaarket.cz",
        "sk": "www.maaarket.sk",
        "pl": "www.maaarket.pl",
        "gr": "www.maaarket.gr",
        "ro": "www.maaarket.ro",
        "bg": "www.maaarket.bg",
    },
    # Add more groups for satellite sites, e.g.:
    # {
    #     "sl": "www.thundershop.si",
    #     "hr": "www.thundershop.hr",
    #     ...
    # },
]

# Path prefix per language (some shops use /izdelek/, others /product/ etc.)
# If all domains use the same path, leave this empty.
PATH_PREFIX_OVERRIDE = {
    # "rs": "/proizvod/",  # example: RS uses different path prefix
}

# ─── XML FEED CONFIG ──────────────────────────────────────────────────────────

FEEDS = {
    "sl": "https://api.maaarket.si/storage/exports/sl/google.xml",
    "hr": "https://api.maaarket.hr/storage/exports/hr/google.xml",
    "rs": "https://api.maaarket.rs/storage/exports/sr/google.xml",
    "hu": "https://api.maaarket.hu/storage/exports/hu/google.xml",
    "pl": "https://api.maaarket.pl/storage/exports/pl/google.xml",
    "cz": "https://api.maaarket.cz/storage/exports/cs/google.xml",
    "sk": "https://api.maaarket.sk/storage/exports/sk/google.xml",
    "gr": "https://api.maaarket.gr/storage/exports/el/google.xml",
    "bg": "https://api.maaarket.bg/storage/exports/bg/google.xml",
    "ro": "https://api.maaarket.ro/storage/exports/ro/google.xml",
}

# ─── IN-MEMORY CACHE ─────────────────────────────────────────────────────────
feed_cache: dict = {}
last_fetch: Optional[datetime] = None
CACHE_TTL_HOURS = 24


def is_cache_stale() -> bool:
    if last_fetch is None:
        return True
    return datetime.now() - last_fetch > timedelta(hours=CACHE_TTL_HOURS)


# ─── URL HELPERS ─────────────────────────────────────────────────────────────

def get_domain_group(domain: str) -> Optional[dict]:
    """Find the domain group that contains this domain."""
    clean = domain.replace("https://", "").replace("http://", "").split("/")[0]
    for group in DOMAIN_GROUPS:
        if clean in group.values():
            return group
    return None


def build_urls_from_slug(source_url: str) -> dict:
    """
    Given a source URL, extract the slug and build URLs for all languages
    by replacing the domain. Returns { lang: url }.
    """
    parsed = urlparse(source_url)
    source_domain = parsed.netloc  # e.g. www.maaarket.si
    path = parsed.path             # e.g. /izdelek/parni-cistilec-vapurex

    group = get_domain_group(source_domain)
    if not group:
        return {}

    result = {}
    for lang, target_domain in group.items():
        # Apply path prefix override if defined
        final_path = path
        if lang in PATH_PREFIX_OVERRIDE:
            # Replace the path prefix (e.g. /izdelek/ → /proizvod/)
            parts = path.split("/")
            if len(parts) >= 3:
                parts[1] = PATH_PREFIX_OVERRIDE[lang].strip("/")
                final_path = "/".join(parts)

        result[lang] = f"{parsed.scheme}://{target_domain}{final_path}"

    return result


def extract_slug(url: str) -> Optional[str]:
    """Extract product slug from URL."""
    for pattern in [r'/izdelek/([^/?#]+)', r'/product/([^/?#]+)', r'/proizvod/([^/?#]+)',
                    r'/termek/([^/?#]+)', r'/produkt/([^/?#]+)', r'/produkty/([^/?#]+)']:
        m = re.search(pattern, url)
        if m:
            return m.group(1).lower()
    return None


# ─── XML FEED PARSING ────────────────────────────────────────────────────────

def parse_feed(xml_content: str, lang: str) -> dict:
    """Parse Google Merchant XML and return {sku: {url, title}} dict."""
    products = {}
    try:
        root = ET.fromstring(xml_content)
        channel = root.find('channel')
        if channel is None:
            return products
        ns_g = 'http://base.google.com/ns/1.0'
        for item in channel.findall('item'):
            link_el = item.find('link')
            url = link_el.text.strip() if link_el is not None and link_el.text else None
            if not url:
                continue
            title_el = item.find('title')
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            gid_el = item.find(f'{{{ns_g}}}id')
            sku = gid_el.text.strip().lower() if gid_el is not None and gid_el.text else None
            slug = extract_slug(url)
            entry = {"url": url, "title": title}
            if sku:
                products[sku] = entry
            if slug and slug != sku:
                products[slug] = entry
    except ET.ParseError as e:
        print(f"XML parse error [{lang}]: {e}")
    return products


async def fetch_all_feeds():
    global feed_cache, last_fetch
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching XML feeds...")
    async with httpx.AsyncClient(timeout=30.0) as hc:
        tasks = {lang: hc.get(url) for lang, url in FEEDS.items()}
        for lang, task in tasks.items():
            try:
                resp = await task
                if resp.status_code == 200:
                    feed_cache[lang] = parse_feed(resp.text, lang)
                    print(f"  ✓ {lang}: {len(feed_cache[lang])} products")
                else:
                    feed_cache[lang] = {}
                    print(f"  ✗ {lang}: HTTP {resp.status_code}")
            except Exception as e:
                feed_cache[lang] = {}
                print(f"  ✗ {lang}: {e}")
    last_fetch = datetime.now()


async def ensure_cache_fresh():
    if is_cache_stale():
        await fetch_all_feeds()


def lookup_by_sku(sku: str) -> dict:
    """Find product URLs across all languages by SKU. Returns {lang: url}."""
    key = sku.strip().lower()
    result = {}
    for lang, products in feed_cache.items():
        if key in products:
            result[lang] = products[key]["url"]
            continue
        # Partial match fallback
        for prod_key, prod_data in products.items():
            if key in prod_key or prod_key in key:
                result[lang] = prod_data["url"]
                break
    return result


# ─── STARTUP ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    await fetch_all_feeds()
    asyncio.create_task(daily_refresh())


async def daily_refresh():
    while True:
        await asyncio.sleep(CACHE_TTL_HOURS * 3600)
        await fetch_all_feeds()


# ─── MODELS ──────────────────────────────────────────────────────────────────

class AdRequest(BaseModel):
    input: str       # product description or URL
    mode: str        # "url" or "text"
    pt_count: int = 1
    hl_count: int = 1
    source_url: Optional[str] = None   # SL product URL for domain mapping
    sku: Optional[str] = None          # SKU for XML lookup fallback


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/cache-status")
async def cache_status():
    return {
        "last_fetch": last_fetch.isoformat() if last_fetch else None,
        "stale": is_cache_stale(),
        "products_per_lang": {lang: len(p) for lang, p in feed_cache.items()}
    }


@app.post("/refresh-cache")
async def refresh_cache():
    await fetch_all_feeds()
    return {"status": "ok", "last_fetch": last_fetch.isoformat()}


@app.post("/generate")
async def generate(req: AdRequest):
    await ensure_cache_fresh()

    # ── Step 1: Resolve product URLs ──
    product_urls = {}

    if req.source_url:
        # Primary: build URLs by replacing domain (no tokens needed)
        product_urls = build_urls_from_slug(req.source_url)

    if req.sku:
        # Fallback/supplement: look up missing langs via XML cache
        sku_urls = lookup_by_sku(req.sku)
        for lang, url in sku_urls.items():
            if lang not in product_urls:
                product_urls[lang] = url

    # ── Step 2: Generate ad copy via Claude ──
    if req.mode == "url":
        user_msg = f"Preberi to stran in ustvari Meta oglase: {req.input}"
    else:
        user_msg = f"Na podlagi tega opisa ustvari Meta oglase:\n\n{req.input}"

    pt_ph = ", ".join([f'"PT {i+1}"' for i in range(req.pt_count)])
    hl_ph = ", ".join([f'"HL {i+1}"' for i in range(req.hl_count)])

    prompt = f"""{user_msg}

OBVEZNO ustvari TOČNO {req.pt_count} Primary Text(ov) IN TOČNO {req.hl_count} Headline(ov) za VSAK jezik.

Primary Text pravila:
- 2-3 kratke vrstice, vsaj 4-5 emoji-jev, energičen prodajni ton, brez cen
- Vsak tekst DRUGAČEN od ostalih

Headline pravila:
- MAKSIMALNO 5 BESED, točno 1 emoji na začetku, brez cen
- Vsak headline DRUGAČEN

Jeziki: SL (izvirnik), HR (latinica), RS (SAMO latinica), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (SAMO cirilica).

Vrni SAMO veljaven JSON brez markdown:
{{
  "product": "kratko ime izdelka",
  "sl": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "hr": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "rs": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "hu": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "cz": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "sk": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "pl": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "gr": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "ro": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}},
  "bg": {{"pt": [{pt_ph}], "hl": [{hl_ph}]}}
}}"""

    tools = [{"type": "web_search_20250305", "name": "web_search"}] if req.mode == "url" else []

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        tools=tools if tools else anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}]
    )

    text = "".join(b.text for b in message.content if hasattr(b, "text"))
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text).strip()

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return {"error": "Claude ni vrnil veljavnega JSON. Poskusi znova."}

    try:
        data = json.loads(match.group())
        data["product_urls"] = product_urls
        return data
    except json.JSONDecodeError as e:
        return {"error": f"JSON napaka: {str(e)}"}
