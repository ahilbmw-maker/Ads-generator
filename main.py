import os
import json
import re
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

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
# Structure: { lang: { sku: { "url": "...", "title": "..." } } }
feed_cache: dict = {}
last_fetch: Optional[datetime] = None
CACHE_TTL_HOURS = 24


def is_cache_stale() -> bool:
    if last_fetch is None:
        return True
    return datetime.now() - last_fetch > timedelta(hours=CACHE_TTL_HOURS)


def extract_sku_from_url(url: str) -> Optional[str]:
    """Extract SKU/slug from product URL. Works for maaarket URLs."""
    # e.g. https://www.maaarket.si/izdelek/parni-cistilec-vapurex-9 -> parni-cistilec-vapurex-9
    match = re.search(r'/izdelek/([^/?#]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/product/([^/?#]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'/proizvod/([^/?#]+)', url)
    if match:
        return match.group(1)
    return None


def parse_feed(xml_content: str, lang: str) -> dict:
    """Parse Google Merchant XML feed and return {sku: {url, title, id}} dict."""
    products = {}
    try:
        root = ET.fromstring(xml_content)
        ns = {
            'g': 'http://base.google.com/ns/1.0'
        }
        channel = root.find('channel')
        if channel is None:
            return products

        for item in channel.findall('item'):
            # Get product link
            link_el = item.find('link')
            url = link_el.text.strip() if link_el is not None and link_el.text else None
            if not url:
                continue

            # Get title
            title_el = item.find('title')
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            # Get g:id (SKU)
            gid_el = item.find('g:id', ns)
            if gid_el is None:
                gid_el = item.find('{http://base.google.com/ns/1.0}id')
            sku = gid_el.text.strip() if gid_el is not None and gid_el.text else None

            # Extract slug from URL as backup key
            slug = extract_sku_from_url(url)

            product_data = {"url": url, "title": title, "sku": sku or ""}

            if sku:
                products[sku.lower()] = product_data
            if slug:
                products[slug.lower()] = product_data

    except ET.ParseError as e:
        print(f"XML parse error for {lang}: {e}")
    return products


async def fetch_all_feeds():
    """Fetch all XML feeds concurrently and update cache."""
    global feed_cache, last_fetch
    print(f"[{datetime.now()}] Fetching XML feeds...")

    async with httpx.AsyncClient(timeout=30.0) as client_http:
        tasks = {
            lang: client_http.get(url)
            for lang, url in FEEDS.items()
        }

        results = {}
        for lang, task in tasks.items():
            try:
                response = await task
                if response.status_code == 200:
                    results[lang] = parse_feed(response.text, lang)
                    print(f"  ✓ {lang}: {len(results[lang])} products")
                else:
                    print(f"  ✗ {lang}: HTTP {response.status_code}")
                    results[lang] = {}
            except Exception as e:
                print(f"  ✗ {lang}: {e}")
                results[lang] = {}

    feed_cache = results
    last_fetch = datetime.now()
    print(f"[{datetime.now()}] Feed cache updated.")


async def ensure_cache_fresh():
    """Refresh cache if stale."""
    if is_cache_stale():
        await fetch_all_feeds()


def find_product_urls(query: str) -> dict:
    """
    Given a URL or SKU, find matching product URLs for all languages.
    Returns { lang: { url, title } } or empty dict if not found.
    """
    # Normalize query
    if query.startswith('http'):
        key = extract_sku_from_url(query)
    else:
        key = query.strip()

    if not key:
        return {}

    key = key.lower()
    result = {}

    for lang, products in feed_cache.items():
        # Try exact match first
        if key in products:
            result[lang] = products[key]
            continue

        # Try partial slug match (in case URL format differs slightly)
        for prod_key, prod_data in products.items():
            if key in prod_key or prod_key in key:
                result[lang] = prod_data
                break

    return result


# ─── STARTUP ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Fetch feeds on startup."""
    await fetch_all_feeds()
    # Schedule daily refresh in background
    asyncio.create_task(daily_refresh())


async def daily_refresh():
    """Background task: refresh feeds every 24 hours."""
    while True:
        await asyncio.sleep(CACHE_TTL_HOURS * 3600)
        await fetch_all_feeds()


# ─── MODELS ──────────────────────────────────────────────────────────────────

class AdRequest(BaseModel):
    input: str
    mode: str
    pt_count: int = 1
    hl_count: int = 1


class LookupRequest(BaseModel):
    query: str  # URL or SKU


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/cache-status")
async def cache_status():
    """Check when cache was last updated and how many products per lang."""
    return {
        "last_fetch": last_fetch.isoformat() if last_fetch else None,
        "next_fetch": (last_fetch + timedelta(hours=CACHE_TTL_HOURS)).isoformat() if last_fetch else None,
        "products_per_lang": {lang: len(prods) for lang, prods in feed_cache.items()},
        "stale": is_cache_stale()
    }


@app.post("/refresh-cache")
async def refresh_cache():
    """Manually trigger a cache refresh."""
    await fetch_all_feeds()
    return {"status": "ok", "last_fetch": last_fetch.isoformat()}


@app.post("/lookup")
async def lookup_product(req: LookupRequest):
    """Find product URLs across all languages for a given URL or SKU."""
    await ensure_cache_fresh()
    urls = find_product_urls(req.query)
    return {
        "query": req.query,
        "found": len(urls) > 0,
        "urls": urls
    }


@app.post("/generate")
async def generate(req: AdRequest):
    await ensure_cache_fresh()

    if req.mode == "url":
        user_msg = f"Preberi to stran in ustvari Meta oglase: {req.input}"
    else:
        user_msg = f"Na podlagi tega opisa ustvari Meta oglase:\n\n{req.input}"

    # Find product URLs for all languages
    product_urls = find_product_urls(req.input) if req.mode == "url" else {}

    pt_placeholders = ", ".join([f'"PT tekst {i+1}"' for i in range(req.pt_count)])
    hl_placeholders = ", ".join([f'"HL tekst {i+1}"' for i in range(req.hl_count)])

    prompt = f"""{user_msg}

OBVEZNO ustvari TOČNO {req.pt_count} Primary Text(ov) IN TOČNO {req.hl_count} Headline(ov) za VSAK jezik.

Pravila za Primary Text (ponovi {req.pt_count}x za vsak jezik):
- 2-3 kratke vrstice
- Vsaj 4-5 emoji-jev razporejenih po besedilu
- Energičen, prodajno usmerjen ton
- Brez cen
- Vsak tekst mora biti DRUGAČEN od ostalih

Pravila za Headline (ponovi {req.hl_count}x za vsak jezik):
- MAKSIMALNO 5 BESED, ne več!
- Točno 1 emoji na začetku
- Brez cen
- Vsak headline mora biti DRUGAČEN

Jeziki: SL (izvirnik), HR (latinica), RS (SAMO latinica), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (SAMO cirilica).

JSON struktura — "pt" mora imeti TOČNO {req.pt_count} elementov, "hl" mora imeti TOČNO {req.hl_count} elementov:
{{
  "product": "kratko ime izdelka",
  "sl": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "hr": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "rs": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "hu": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "cz": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "sk": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "pl": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "gr": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "ro": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}},
  "bg": {{"pt": [{pt_placeholders}], "hl": [{hl_placeholders}]}}
}}

Vrni SAMO veljaven JSON, brez markdown, brez ```."""

    tools = [{"type": "web_search_20250305", "name": "web_search"}] if req.mode == "url" else []

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        tools=tools if tools else anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}]
    )

    text = ""
    for block in message.content:
        if hasattr(block, "text"):
            text += block.text

    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return {"error": "Claude ni vrnil veljavnega JSON. Poskusi znova."}

    try:
        data = json.loads(match.group())
        # Attach product URLs to response
        data["product_urls"] = {
            lang: info["url"]
            for lang, info in product_urls.items()
        }
        return data
    except json.JSONDecodeError as e:
        return {"error": f"JSON napaka: {str(e)}"}
