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

G = "http://base.google.com/ns/1.0"

# ─── CACHE STRUCTURE ─────────────────────────────────────────────────────────
# feed_by_lang:  { lang: { g_id: { url, path } } }   — lookup by g:id
# slug_to_id:    { slug: g_id }                       — SL slug → g:id mapping

feed_by_lang: dict = {}   # { lang: { g_id: { url, path } } }
slug_to_id: dict = {}     # { slug: g_id } — built from SL feed

last_fetch: Optional[datetime] = None
CACHE_TTL_HOURS = 24


def is_cache_stale() -> bool:
    return last_fetch is None or datetime.now() - last_fetch > timedelta(hours=CACHE_TTL_HOURS)


def extract_slug(url: str) -> Optional[str]:
    """Extract last path segment (product slug) from any product URL."""
    path = urlparse(url).path.rstrip('/')
    parts = [p for p in path.split('/') if p]
    return parts[-1].lower() if parts else None


def parse_feed(xml_content: str) -> dict:
    """
    Parse Google Merchant XML.
    Returns { g_id: { url, path } }
    g:id is the numeric product ID (e.g. "23166").
    """
    products = {}
    try:
        root = ET.fromstring(xml_content)
        channel = root.find('channel')
        if channel is None:
            return products
        for item in channel.findall('item'):
            gid_el = item.find(f'{{{G}}}id')
            link_el = item.find(f'{{{G}}}link')
            if gid_el is None or not gid_el.text:
                continue
            if link_el is None or not link_el.text:
                continue
            g_id = gid_el.text.strip()
            url = link_el.text.strip()
            path = urlparse(url).path
            products[g_id] = {"url": url, "path": path}
    except ET.ParseError as e:
        print(f"XML parse error: {e}")
    return products


async def fetch_all_feeds():
    global feed_by_lang, slug_to_id, last_fetch
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching XML feeds...")

    async with httpx.AsyncClient(timeout=30.0) as hc:
        tasks = {lang: hc.get(url) for lang, url in MAAARKET_FEEDS.items()}
        new_cache = {}
        for lang, task in tasks.items():
            try:
                resp = await task
                if resp.status_code == 200:
                    new_cache[lang] = parse_feed(resp.text)
                    print(f"  ✓ {lang}: {len(new_cache[lang])} products")
                else:
                    new_cache[lang] = {}
                    print(f"  ✗ {lang}: HTTP {resp.status_code}")
            except Exception as e:
                new_cache[lang] = {}
                print(f"  ✗ {lang}: {e}")

    feed_by_lang = new_cache

    # Build slug→g:id index from ALL language feeds
    # This allows lookup regardless of which language URL is entered
    new_slug_to_id = {}
    for lang, lang_feed in new_cache.items():
        for g_id, data in lang_feed.items():
            slug = extract_slug(data["url"])
            if slug and slug not in new_slug_to_id:
                new_slug_to_id[slug] = g_id
    slug_to_id = new_slug_to_id

    last_fetch = datetime.now()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done. Slug index: {len(slug_to_id)} entries across all langs.")


async def ensure_cache_fresh():
    if is_cache_stale():
        await fetch_all_feeds()


def detect_brand(url: str) -> Optional[str]:
    if not url:
        return None
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for brand, lang_map in BRAND_DOMAINS.items():
        for d in lang_map.values():
            if domain == d.replace("www.", ""):
                return brand
    return None


def find_product_urls(source_url: Optional[str]) -> dict:
    """
    1. Extract slug from source_url
    2. Look up slug in SL slug→g:id index → get g:id
    3. For each lang: find g:id in that lang's feed → get local path
    4. If satellite brand: replace maaarket domain with brand domain
       (path stays the same since slugs are identical across brands)

    Returns { lang: full_url }
    """
    if not source_url:
        return {}

    brand = detect_brand(source_url) or "maaarket"

    # Normalise: always look up slug against SL maaarket index
    slug = extract_slug(source_url)
    if not slug:
        return {}

    # Step 1: slug → g:id (from SL feed)
    g_id = slug_to_id.get(slug)
    if not g_id:
        print(f"  Slug '{slug}' not found in SL index.")
        return {}

    print(f"  Slug '{slug}' → g:id {g_id}")

    target_domains = BRAND_DOMAINS.get(brand, BRAND_DOMAINS["maaarket"])
    result = {}

    # Step 2: for each lang find g:id → get path
    for lang, products in feed_by_lang.items():
        if lang not in target_domains:
            continue
        if g_id not in products:
            continue
        path = products[g_id]["path"]
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


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/cache-status")
async def cache_status():
    return {
        "last_fetch": last_fetch.isoformat() if last_fetch else None,
        "stale": is_cache_stale(),
        "products_per_lang": {lang: len(p) for lang, p in feed_by_lang.items()},
        "sl_slug_index_size": len(slug_to_id),
    }


@app.post("/refresh-cache")
async def refresh_cache():
    await fetch_all_feeds()
    return {"status": "ok", "last_fetch": last_fetch.isoformat()}


@app.post("/lookup-debug")
async def lookup_debug(data: dict):
    """Debug: test URL lookup without generating ads."""
    await ensure_cache_fresh()
    source_url = data.get("source_url", "")
    slug = extract_slug(source_url)
    g_id = slug_to_id.get(slug) if slug else None
    urls = find_product_urls(source_url)
    return {
        "source_url": source_url,
        "brand": detect_brand(source_url),
        "slug": slug,
        "g_id": g_id,
        "found_urls": urls,
        "sl_index_sample": dict(list(slug_to_id.items())[:5]),
    }


@app.post("/generate")
async def generate(req: AdRequest):
    await ensure_cache_fresh()

    product_urls = find_product_urls(req.source_url)

    if req.mode == "url":
        user_msg = f"Preberi to stran in ustvari Meta oglase: {req.input}"
    else:
        user_msg = f"Na podlagi tega opisa ustvari Meta oglase:\n\n{req.input}"

    pt_ph = ", ".join([f'"PT {i+1}"' for i in range(req.pt_count)])
    hl_ph = ", ".join([f'"HL {i+1}"' for i in range(req.hl_count)])

    prompt = f"""{user_msg}

OBVEZNO ustvari TOČNO {req.pt_count} Primary Text(ov) IN TOČNO {req.hl_count} Headline(ov) za VSAK jezik.

Primary Text pravila:
- 2-3 kratke vrstice, vsaj 2-3 emoji-jev, energičen prodajni ton, brez cen
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

    # Robust JSON extraction
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return {"error": "Claude ni vrnil veljavnega JSON. Poskusi znova."}

    try:
        data = json.loads(match.group())
        data["product_urls"] = product_urls
        return data
    except json.JSONDecodeError as e:
        return {"error": f"JSON napaka: {str(e)}"}
