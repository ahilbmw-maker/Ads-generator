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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── BRAND DOMAIN MAPS ───────────────────────────────────────────────────────

BRAND_DOMAINS = {
    "maaarket": {
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
    "fluxigo": {
        "sl": "www.fluxigo.si",
        "hr": "www.fluxigo.hr",
        "rs": "www.fluxigo.rs",
        "hu": "www.fluxigo.hu",
        "cz": "www.fluxigo.cz",
        "sk": "www.fluxigo.sk",
        "pl": "www.fluxigo.pl",
        "gr": "www.fluxigo.gr",
        "ro": "www.fluxigo.ro",
        "bg": "www.fluxigo.bg",
    },
    "easyzo": {
        "sl": "www.easyzo.si",
        "hr": "www.easyzo.hr",
        "rs": "www.easyzo.rs",
        "hu": "www.easyzo.hu",
        "cz": "www.easyzo.cz",
        "sk": "www.easyzo.sk",
        "pl": "www.easyzo.pl",
        "gr": "www.easyzo.gr",
        "ro": "www.easyzo.ro",
        "bg": "www.easyzo.bg",
    },
    "zipply": {
        "sl": "www.zipply.si",
        "hr": "www.zipply.hr",
        "rs": "www.zipply.rs",
        "hu": "www.zipply.hu",
        "cz": "www.zipply.cz",
        "sk": "www.zipply.sk",
        "pl": "www.zipply.pl",
        "gr": "www.zipply.gr",
        "ro": "www.zipply.ro",
        "bg": "www.zipply.bg",
    },
    "thundershop": {
        "sl": "www.thundershop.si",
        "hr": "www.thundershop.hr",
        "rs": "www.thundershop.rs",
        "hu": "www.thundershop.hu",
        "cz": "www.thundershop.cz",
        "sk": "www.thundershop.sk",
        "gr": "www.thundershop.gr",
        "ro": "www.thundershop.ro",
        "bg": "www.thundershop.bg",
    },
    "colibrishop": {
        "sl": "www.colibrishop.si",
        "hr": "www.colibrishop.hr",
        "rs": "www.colibrishop.rs",
        "cz": "www.colibrishop.cz",
        "sk": "www.colibrishop.sk",
        "gr": "www.colibrishop.gr",
        "ro": "www.colibrishop.ro",
        "bg": "www.colibrishop.bg",
    },
}

# ─── MAAARKET XML FEEDS ───────────────────────────────────────────────────────

MAAARKET_FEEDS = {
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

# Google Merchant XML namespace
G = "http://base.google.com/ns/1.0"

# ─── CACHE ───────────────────────────────────────────────────────────────────

feed_cache: dict = {}
last_fetch: Optional[datetime] = None
CACHE_TTL_HOURS = 24


def is_cache_stale() -> bool:
    return last_fetch is None or datetime.now() - last_fetch > timedelta(hours=CACHE_TTL_HOURS)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def detect_brand(url: str) -> Optional[str]:
    if not url:
        return None
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for brand, lang_map in BRAND_DOMAINS.items():
        for d in lang_map.values():
            if domain == d.replace("www.", ""):
                return brand
    return None


def extract_slug(url: str) -> Optional[str]:
    for pattern in [
        r'/izdelek/([^/?#]+)',
        r'/product/([^/?#]+)',
        r'/proizvod/([^/?#]+)',
        r'/termek/([^/?#]+)',
        r'/produkt/([^/?#]+)',
        r'/produkty/([^/?#]+)',
        r'/item/([^/?#]+)',
        r'/tovar/([^/?#]+)',
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1).lower()
    return None


def parse_feed(xml_content: str) -> dict:
    """
    Parse Google Merchant XML feed.
    Fields are under g: namespace: <g:id>, <g:link>, <g:title>
    Returns { key: { url, path, title, sku } }
    Indexed by both g:id (numeric SKU) and URL slug.
    """
    products = {}
    try:
        root = ET.fromstring(xml_content)
        channel = root.find('channel')
        if channel is None:
            return products

        for item in channel.findall('item'):
            # g:link is the product URL
            link_el = item.find(f'{{{G}}}link')
            url = link_el.text.strip() if link_el is not None and link_el.text else None
            if not url:
                continue

            parsed = urlparse(url)
            path = parsed.path  # e.g. /izdelek/parni-cistilec-vapurex

            # g:title
            title_el = item.find(f'{{{G}}}title')
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            # g:id — numeric product ID / SKU
            gid_el = item.find(f'{{{G}}}id')
            sku = gid_el.text.strip() if gid_el is not None and gid_el.text else None

            slug = extract_slug(url)
            entry = {"url": url, "path": path, "title": title, "sku": sku or ""}

            # Index by SKU (numeric id)
            if sku:
                products[sku.lower()] = entry

            # Index by slug (URL slug)
            if slug and slug != (sku or "").lower():
                products[slug] = entry

    except ET.ParseError as e:
        print(f"XML parse error: {e}")
    return products


async def fetch_all_feeds():
    global feed_cache, last_fetch
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching maaarket XML feeds...")
    async with httpx.AsyncClient(timeout=30.0) as hc:
        tasks = {lang: hc.get(url) for lang, url in MAAARKET_FEEDS.items()}
        for lang, task in tasks.items():
            try:
                resp = await task
                if resp.status_code == 200:
                    feed_cache[lang] = parse_feed(resp.text)
                    print(f"  ✓ {lang}: {len(feed_cache[lang])} products")
                else:
                    feed_cache[lang] = {}
                    print(f"  ✗ {lang}: HTTP {resp.status_code}")
            except Exception as e:
                feed_cache[lang] = {}
                print(f"  ✗ {lang}: {e}")
    last_fetch = datetime.now()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Feed cache updated.")


async def ensure_cache_fresh():
    if is_cache_stale():
        await fetch_all_feeds()


def find_product_urls(source_url: Optional[str], sku: Optional[str]) -> dict:
    """
    1. Detect brand from source_url
    2. Lookup key = SKU (preferred) or slug from URL
    3. Find path in maaarket XML cache for each lang
    4. Build final URL: target brand domain + maaarket path
    """
    brand = detect_brand(source_url) if source_url else None
    if not brand:
        brand = "maaarket"

    lookup_key = None
    if sku and sku.strip():
        lookup_key = sku.strip().lower()
    elif source_url:
        lookup_key = extract_slug(source_url)

    if not lookup_key:
        return {}

    target_domains = BRAND_DOMAINS.get(brand, BRAND_DOMAINS["maaarket"])
    result = {}

    for lang, products in feed_cache.items():
        entry = None

        # Exact match
        if lookup_key in products:
            entry = products[lookup_key]
        else:
            # Partial match fallback
            for prod_key, prod_data in products.items():
                if lookup_key in prod_key or prod_key in lookup_key:
                    entry = prod_data
                    break

        if not entry:
            continue

        path = entry["path"]

        if lang in target_domains:
            result[lang] = f"https://{target_domains[lang]}{path}"

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
    input: str
    mode: str
    pt_count: int = 1
    hl_count: int = 1
    source_url: Optional[str] = None
    sku: Optional[str] = None


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


@app.post("/lookup-debug")
async def lookup_debug(data: dict):
    """Debug endpoint: test SKU/URL lookup without generating ads."""
    await ensure_cache_fresh()
    source_url = data.get("source_url")
    sku = data.get("sku")
    urls = find_product_urls(source_url, sku)
    brand = detect_brand(source_url) if source_url else "maaarket"
    slug = extract_slug(source_url) if source_url else None
    lookup_key = sku.strip().lower() if sku else slug
    # Show first 5 cache keys per lang for debugging
    sample = {lang: list(products.keys())[:5] for lang, products in feed_cache.items()}
    return {
        "brand": brand,
        "lookup_key": lookup_key,
        "found_urls": urls,
        "cache_sample_keys": sample
    }


@app.post("/generate")
async def generate(req: AdRequest):
    await ensure_cache_fresh()

    product_urls = find_product_urls(req.source_url, req.sku)

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
