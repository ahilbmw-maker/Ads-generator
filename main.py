import os
import json
import re
import asyncio
import shutil
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import urlparse
from pathlib import Path

import httpx
import openpyxl
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import anthropic

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TEMPLATE_PATH = "static/tiktok_template.xlsx"
EXPORTS_DIR = Path("exports")
EXPORTS_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(exist_ok=True, parents=True)
TT_HISTORY_FILE = DATA_DIR / "tiktok_history.json"
META_HISTORY_FILE = DATA_DIR / "meta_history.json"
KREATIVE_HISTORY_FILE = DATA_DIR / "kreative_history.json"
FORECAST_ENTRIES_FILE = DATA_DIR / "forecast_entries.json"
FORECAST_HISTORY_FILE = DATA_DIR / "forecast_history.json"

# ─── BRAND DOMAIN MAPS ───────────────────────────────────────────────────────

BRAND_DOMAINS = {
    "maaarket": {"sl":"www.maaarket.si","hr":"www.maaarket.hr","rs":"www.maaarket.rs","hu":"www.maaarket.hu","cz":"www.maaarket.cz","sk":"www.maaarket.sk","pl":"www.maaarket.pl","gr":"www.maaarket.gr","ro":"www.maaarket.ro","bg":"www.maaarket.bg"},
    "fluxigo":  {"sl":"www.fluxigo.si","hr":"www.fluxigo.hr","rs":"www.fluxigo.rs","hu":"www.fluxigo.hu","cz":"www.fluxigo.cz","sk":"www.fluxigo.sk","pl":"www.fluxigo.pl","gr":"www.fluxigo.gr","ro":"www.fluxigo.ro","bg":"www.fluxigo.bg"},
    "easyzo":   {"sl":"www.easyzo.si","hr":"www.easyzo.hr","rs":"www.easyzo.rs","hu":"www.easyzo.hu","cz":"www.easyzo.cz","sk":"www.easyzo.sk","pl":"www.easyzo.pl","gr":"www.easyzo.gr","ro":"www.easyzo.ro","bg":"www.easyzo.bg"},
    "zipply":   {"sl":"www.zipply.si","hr":"www.zipply.hr","rs":"www.zipply.rs","hu":"www.zipply.hu","cz":"www.zipply.cz","sk":"www.zipply.sk","pl":"www.zipply.pl","gr":"www.zipply.gr","ro":"www.zipply.ro","bg":"www.zipply.bg"},
    "thundershop": {"sl":"www.thundershop.si","hr":"www.thundershop.hr","rs":"www.thundershop.rs","hu":"www.thundershop.hu","cz":"www.thundershop.cz","sk":"www.thundershop.sk","gr":"www.thundershop.gr","ro":"www.thundershop.ro","bg":"www.thundershop.bg"},
    "colibrishop": {"sl":"www.colibrishop.si","hr":"www.colibrishop.hr","rs":"www.colibrishop.rs","cz":"www.colibrishop.cz","sk":"www.colibrishop.sk","gr":"www.colibrishop.gr","ro":"www.colibrishop.ro","bg":"www.colibrishop.bg"},
}

MAAARKET_FEEDS = {
    "sl":"https://api.maaarket.si/storage/exports/sl/google.xml",
    "hr":"https://api.maaarket.hr/storage/exports/hr/google.xml",
    "rs":"https://api.maaarket.rs/storage/exports/sr/google.xml",
    "hu":"https://api.maaarket.hu/storage/exports/hu/google.xml",
    "pl":"https://api.maaarket.pl/storage/exports/pl/google.xml",
    "cz":"https://api.maaarket.cz/storage/exports/cs/google.xml",
    "sk":"https://api.maaarket.sk/storage/exports/sk/google.xml",
    "gr":"https://api.maaarket.gr/storage/exports/el/google.xml",
    "bg":"https://api.maaarket.bg/storage/exports/bg/google.xml",
    "ro":"https://api.maaarket.ro/storage/exports/ro/google.xml",
}

G = "http://base.google.com/ns/1.0"
feed_by_lang: dict = {}
slug_to_id: dict = {}
last_fetch: Optional[datetime] = None
CACHE_TTL_HOURS = 24


def is_cache_stale():
    return last_fetch is None or datetime.now() - last_fetch > timedelta(hours=CACHE_TTL_HOURS)


def extract_slug(url: str) -> Optional[str]:
    path = urlparse(url).path.rstrip('/')
    parts = [p for p in path.split('/') if p]
    return parts[-1].lower() if parts else None


def parse_feed(xml_content: str) -> dict:
    products = {}
    try:
        root = ET.fromstring(xml_content)
        channel = root.find('channel')
        if channel is None:
            return products
        for item in channel.findall('item'):
            gid_el = item.find(f'{{{G}}}id')
            link_el = item.find(f'{{{G}}}link')
            if gid_el is None or not gid_el.text or link_el is None or not link_el.text:
                continue
            g_id = gid_el.text.strip()
            url = link_el.text.strip()
            path = urlparse(url).path
            products[g_id] = {"url": url, "path": path}
    except ET.ParseError:
        pass
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
                new_cache[lang] = parse_feed(resp.text) if resp.status_code == 200 else {}
                print(f"  ✓ {lang}: {len(new_cache.get(lang,{}))} products")
            except Exception as e:
                new_cache[lang] = {}
                print(f"  ✗ {lang}: {e}")
    feed_by_lang = new_cache
    new_slug_to_id = {}
    for lang, lang_feed in feed_by_lang.items():
        for g_id, data in lang_feed.items():
            slug = extract_slug(data["url"])
            if slug and slug not in new_slug_to_id:
                new_slug_to_id[slug] = g_id
    slug_to_id = new_slug_to_id
    last_fetch = datetime.now()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done. Slug index: {len(slug_to_id)}")


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
    if not source_url:
        return {}
    brand = detect_brand(source_url) or "maaarket"
    slug = extract_slug(source_url)
    if not slug:
        return {}
    g_id = slug_to_id.get(slug)
    if not g_id:
        return {}
    target_domains = BRAND_DOMAINS.get(brand, BRAND_DOMAINS["maaarket"])
    result = {}
    for lang, products in feed_by_lang.items():
        if lang not in target_domains or g_id not in products:
            continue
        result[lang] = f"https://{target_domains[lang]}{products[g_id]['path']}"
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


# ─── PROMPT BUILDERS ─────────────────────────────────────────────────────────

def build_meta_prompt(user_msg: str, pt_count: int, hl_count: int) -> str:
    pt_ph = ", ".join([f'"PT {i+1}"' for i in range(pt_count)])
    hl_ph = ", ".join([f'"HL {i+1}"' for i in range(hl_count)])
    return f"""{user_msg}

Ustvari Meta oglase za FB/Instagram v 10 jezikih.

Primary Text ({pt_count}x na jezik): 2-3 vrstice, 2-3 emoji-ji, prodajni ton, brez cen, vsak DRUGAČEN.
Headline ({hl_count}x na jezik): MAX 5 BESED, 1 emoji na začetku, brez cen, vsak DRUGAČEN.
EMOJI PRAVILO: Uporabljaj SAMO te emoji-je ki so zagotovo podprti na vseh napravah:
✅ ⭐ 🔥 💪 🎯 👍 ❤️ 💥 🚀 ✨ 💡 🎁 💰 👌 🙌 😍 💎 🏆 ⚡ 🌟 👏 💫 🛒 📦 🔑 💯 😊 🤩 🌿 🌱 🍃 🌸 🌻 🌞 🍀 🎉 🎊 🛍️ 💚 💙 🧡 💜 🤍 🖤
NE uporabljaj: redkih, novejših ali manj znanih emoji-jev ki se lahko prikažejo kot □

Jeziki: SL (izvirnik), HR (latinica), RS (SAMO latinica!), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (SAMO cirilica!).

Vrni SAMO JSON brez markdown:
{{
  "product": "ime",
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


def build_tiktok_prompt(user_msg: str) -> str:
    return f"""{user_msg}

Ustvari TikTok oglasne tekste v 10 jezikih.

Pravila:
- Točno 4 variante na jezik
- Vsaka varianta MAX 80 znakov (strogo!)
- Brez emojiev, brez # in {{}}
- Kratek, direkten, akcijski stil
- Vsaka varianta drugačen pristop (korist, socialni dokaz, nujnost, radovednost)
- Brez "kakovost/dostava/zaloga" strukture — bodi kreativen

Jeziki: SL (izvirnik), HR (latinica), RS (SAMO latinica!), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (SAMO cirilica!).

KRITIČNO VAŽNO: Vrni IZKLJUČNO in SAMO JSON — nobenih uvodnih besed, nobenih razlag, nobenih komentarjev, nobenih markdown backticks. Prva in zadnja stvar v odgovoru mora biti {{ in }}. Nič drugega.
{{
  "product": "ime",
  "sl": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "hr": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "rs": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "hu": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "cz": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "sk": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "pl": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "gr": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "ro": "[tekst1],[tekst2],[tekst3],[tekst4]",
  "bg": "[tekst1],[tekst2],[tekst3],[tekst4]"
}}\n"""


# ─── GENERATE HELPERS ────────────────────────────────────────────────────────

def parse_json_response(text: str) -> Optional[dict]:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text).strip()
    # Try direct parse first
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    json_str = match.group()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix truncated JSON by finding last complete key-value
        try:
            # Remove trailing incomplete content after last complete string value
            fixed = re.sub(r',\s*"[^"]*":\s*"[^"]*$', '', json_str)
            fixed = re.sub(r',\s*"[^"]*":\s*$', '', fixed)
            if not fixed.endswith('}'):
                fixed = fixed.rstrip(',\n\r\t ') + '}'
            return json.loads(fixed)
        except Exception:
            return None


async def call_claude(prompt: str, model: str, tools=None, max_tokens: int = 8000) -> str:
    loop = asyncio.get_event_loop()
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if tools:
        kwargs["tools"] = tools

    for attempt in range(3):
        try:
            msg = await loop.run_in_executor(None, lambda: client.messages.create(**kwargs))
            return "".join(b.text for b in msg.content if hasattr(b, "text"))
        except anthropic.RateLimitError:
            if attempt < 2:
                wait = (attempt + 1) * 20
                print(f"  Rate limit, waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise
        except Exception as e:
            raise
    return ""


async def generate_meta_sl_only(user_msg: str, mode: str, source_url: Optional[str],
                                pt_count: int, hl_count: int) -> dict:
    """Generira samo SL tekste brez prevajanja — za streaming mode."""
    product_urls = find_product_urls(source_url)
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if mode == "url" else []
    pt_ph = ", ".join([f'"PT {i+1}"' for i in range(pt_count)])
    hl_ph = ", ".join([f'"HL {i+1}"' for i in range(hl_count)])
    sl_prompt = f"""{user_msg}

Ustvari Meta oglase SAMO v slovenščini.
Primary Text ({pt_count}x): 2-3 vrstice, 2-3 emoji-ji, prodajni ton, brez cen, vsak DRUGAČEN.
Headline ({hl_count}x): MAX 5 BESED, 1 emoji na začetku, brez cen, vsak DRUGAČEN.
EMOJI PRAVILO: Uporabljaj SAMO te emoji-je ki so zagotovo podprti na vseh napravah:
✅ ⭐ 🔥 💪 🎯 👍 ❤️ 💥 🚀 ✨ 💡 🎁 💰 👌 🙌 😍 💎 🏆 ⚡ 🌟 👏 💫 🛒 📦 🔑 💯 😊 🤩 🌿 🌱 🍃 🌸 🌻 🌞 🍀 🎉 🎊 🛍️ 💚 💙 🧡 💜 🤍 🖤
NE uporabljaj: redkih, novejših ali manj znanih emoji-jev ki se lahko prikažejo kot □
Vrni SAMO JSON: {{"product": "ime", "pt": [{pt_ph}], "hl": [{hl_ph}]}}"""

    sl_text = await call_claude(sl_prompt, "claude-sonnet-4-6", tools if tools else None, 4000)
    sl_data = parse_json_response(sl_text)
    if not sl_data:
        return {"error": "Napaka pri generiranju SL tekstov."}
    return {
        "product": sl_data.get("product", "Izdelek"),
        "sl": {"pt": sl_data.get("pt", []), "hl": sl_data.get("hl", [])},
        "product_urls": product_urls,
    }


async def generate_meta_one(user_msg: str, mode: str, source_url: Optional[str],
                            pt_count: int, hl_count: int, qmode: str) -> dict:
    product_urls = find_product_urls(source_url)
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if mode == "url" else []

    if qmode == "fast":
        pt_ph = ", ".join([f'"PT {i+1}"' for i in range(pt_count)])
        hl_ph = ", ".join([f'"HL {i+1}"' for i in range(hl_count)])
        sl_prompt = f"""{user_msg}

Ustvari Meta oglase SAMO v slovenščini.
Primary Text ({pt_count}x): 2-3 vrstice, 2-3 emoji-ji, prodajni ton, brez cen, vsak DRUGAČEN.
Headline ({hl_count}x): MAX 5 BESED, 1 emoji na začetku, brez cen, vsak DRUGAČEN.
EMOJI PRAVILO: Uporabljaj SAMO te emoji-je ki so zagotovo podprti na vseh napravah:
✅ ⭐ 🔥 💪 🎯 👍 ❤️ 💥 🚀 ✨ 💡 🎁 💰 👌 🙌 😍 💎 🏆 ⚡ 🌟 👏 💫 🛒 📦 🔑 💯 😊 🤩 🌿 🌱 🍃 🌸 🌻 🌞 🍀 🎉 🎊 🛍️ 💚 💙 🧡 💜 🤍 🖤 🟢 🔵 🟡
NE uporabljaj: redkih, novejših ali manj znanih emoji-jev ki se lahko prikažejo kot □
Vrni SAMO JSON: {{"product": "ime", "pt": [{pt_ph}], "hl": [{hl_ph}]}}"""

        sl_text = await call_claude(sl_prompt, "claude-sonnet-4-6", tools if tools else None, 4000)
        sl_data = parse_json_response(sl_text)
        if not sl_data:
            print(f"SL parse failed. Raw response: {sl_text[:500]}")
            return {"error": "Napaka pri generiranju SL tekstov."}

        sl_pts = sl_data.get("pt", [])
        sl_hls = sl_data.get("hl", [])
        trans_prompt = f"""Prevedi Meta oglase iz slovenščine v 9 jezikov. Ohrani ŠTEVILO in POZICIJO emoji-jev točno kot v originalu.

Primary Texts: {json.dumps(sl_pts, ensure_ascii=False)}
Headlines: {json.dumps(sl_hls, ensure_ascii=False)}

PRAVILA PREVAJANJA PO JEZIKIH:

HR (hrvaščina, latinica): Natural marketing ton. Pazi na "č/ć/š/ž/đ".

RS (srbščina, SAMO LATINICA — NIKOLI cirilica!): Natural marketing ton. Pazi na "č/ć/š/ž/đ".

HU (madžarščina): KRITIČNO - to ni indoevropski jezik, NE prevajaj dobesedno. Uporabljaj aglutinacijo (končnice) pravilno. CTA kot "Naroči zdaj" = "Rendeld meg most". Pazi da stavek ni predolg (madžarski stavki so lahko za 20-30% daljši).

CZ (češčina): Natural. Pazi na sklonjenje samostalnikov (akuzativ po glagolih).

SK (slovaščina): Podobno češčini. Natural.

PL (poljščina): Pazi na sklone (7 padežev). CTA "Naroči" = "Zamów". Uporabi neformalni ti-vi.

GR (grščina, grška pisava!): KRITIČNO - kompleksna slovnica s skloni (nominativ/akuzativ). CTA "Naroči zdaj" = "Παράγγειλε τώρα". Izogibaj se predolgih stavkov. Pazi na spol samostalnikov. Uporabljaj natural marketing grščino, ne dobesedni prevod.

RO (romunščina, latinica): Natural. Pazi na "ă/â/î/ș/ț". CTA "Naroči" = "Comandă".

BG (bolgarščina, SAMO CIRILICA — NIKOLI latinica!): Natural. CTA "Naroči" = "Поръчай".

SPLOŠNA PRAVILA:
- Ohrani prodajni/energičen ton
- Prevodi morajo zveneti kot da jih je pisal materni govorec, ne robot
- Ohrani ŠTEVILO emoji-jev (če ima SL 3 emoji, mora imeti tudi prevod 3)
- Headlines: ohrani MAX 5 besed tudi v prevodu
- Ne prevajaj blagovnih znamk, imen izdelkov, če so v originalu

Vrni SAMO JSON:
{{"hr":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"rs":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"hu":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"cz":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"sk":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"pl":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"gr":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"ro":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}},"bg":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}}}}"""

        trans_text = await call_claude(trans_prompt, "claude-haiku-4-5-20251001", None, 6000)
        trans_data = parse_json_response(trans_text)
        if not trans_data:
            return {"error": "Napaka pri prevajanju."}

        result = {"product": sl_data.get("product","Izdelek"), "sl": {"pt": sl_pts, "hl": sl_hls}, "product_urls": product_urls}
        result.update(trans_data)
        return result
    else:
        prompt = build_meta_prompt(user_msg, pt_count, hl_count)
        text = await call_claude(prompt, "claude-sonnet-4-6", tools if tools else None)
        data = parse_json_response(text)
        if not data:
            return {"error": "Claude ni vrnil veljavnega JSON."}
        data["product_urls"] = product_urls
        return data


async def generate_tiktok_one(user_msg: str, mode: str, source_url: Optional[str]) -> dict:
    product_urls = find_product_urls(source_url)
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if mode == "url" else []
    prompt = build_tiktok_prompt(user_msg)
    text = await call_claude(prompt, "claude-sonnet-4-6", tools if tools else None)
    data = parse_json_response(text)
    if not data:
        print(f"TikTok JSON parse failed. Raw (first 800 chars): {text[:800]}")
        return {"error": "Claude ni vrnil veljavnega JSON."}
    data["product_urls"] = product_urls
    return data


# ─── TIKTOK XLSX BUILDER ─────────────────────────────────────────────────────

COUNTRY_TO_LANG = {
    "BG": "bg", "CZ": "cz", "GR": "gr", "SK": "sk", "RS": "rs",
    "RO": "ro", "HU": "hu", "HR": "hr", "PL": "pl", "SLO": "sl"
}


def build_tiktok_xlsx(sku: str, brand: str, video_names: str,
                      texts_by_lang: dict, urls_by_lang: dict,
                      skip_rs: bool = False) -> str:
    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError("TikTok template not found. Upload tiktok_template.xlsx to static/")

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    ws = wb['Ads']
    headers = [cell.value for cell in ws[1]]

    col_campaign = headers.index('Campaign Name') + 1
    col_bc_id    = headers.index('Business Center ID of the identity') + 1
    col_video    = headers.index('Video Name') + 1
    col_text     = headers.index('Text') + 1
    col_url      = headers.index('Web URL') + 1
    col_ag       = headers.index('Ad Group Name') + 1

    # Get base single BC ID from row 2
    base_bc_raw = ws.cell(row=2, column=col_bc_id).value or ''
    single_id = base_bc_raw.split(',')[0].strip()

    # Count videos to build matching BC ID
    videos = [v.strip() for v in re.findall(r'\[([^\]]+)\]', video_names)]
    new_bc_id = ','.join([single_id] * len(videos)) if videos else single_id
    today = datetime.now().strftime('%-d_%-m_%Y')
    new_campaign = f'[{brand}] Smart+ {sku} - {today}'

    # Zberemo vse template vrstice najprej
    tmpl_data = []
    for row in ws.iter_rows(min_row=2):
        r = row[0].row
        country = ws.cell(row=r, column=col_ag).value
        if not country:
            continue
        lang = COUNTRY_TO_LANG.get(country)
        if skip_rs and lang == 'rs':
            continue
        row_vals = [ws.cell(row=r, column=c+1).value for c in range(len(headers))]
        tmpl_data.append({'country': country, 'lang': lang, 'row_vals': row_vals})

    # Počisti vse vrstice razen headerja
    ws.delete_rows(2, ws.max_row)

    # Ustvari novo vrstico za vsako varianto
    out_row = 2
    fallback_url = next(iter(urls_by_lang.values()), '') if urls_by_lang else ''
    for td in tmpl_data:
        lang = td['lang']
        raw_text = texts_by_lang.get(lang, '') if lang else ''
        # Split variante: [tekst1],[tekst2],[tekst3],[tekst4]
        variants = [v.strip() for v in re.findall(r'\[([^\]]+)\]', raw_text)] if raw_text else [raw_text]
        if not variants:
            variants = [raw_text]
        url = (urls_by_lang.get(lang) if lang else None) or fallback_url

        for variant in variants:
            # Kopiraj vse originalne vrednosti
            for c_idx, val in enumerate(td['row_vals'], 1):
                ws.cell(row=out_row, column=c_idx).value = val
            # Prepiši naše vrednosti
            ws.cell(row=out_row, column=col_campaign).value = new_campaign
            ws.cell(row=out_row, column=col_bc_id).value = new_bc_id
            ws.cell(row=out_row, column=col_video).value = video_names
            ws.cell(row=out_row, column=col_text).value = variant
            if url:
                ws.cell(row=out_row, column=col_url).value = url
            out_row += 1

    out_path = str(EXPORTS_DIR / f"tiktok_{sku}_{uuid.uuid4().hex[:8]}.xlsx")
    wb.save(out_path)
    return out_path


# ─── MODELS ──────────────────────────────────────────────────────────────────

def build_master_xlsx(skus: list) -> str:
    """Združi več SKU-jev v en master XLS — vsak SKU doda svoje vrstice (koliko jih je v template-u)."""
    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError("TikTok template not found.")

    # Load template to get headers and template rows
    wb_tmpl = openpyxl.load_workbook(TEMPLATE_PATH)
    ws_tmpl = wb_tmpl['Ads']
    headers = [cell.value for cell in ws_tmpl[1]]

    col_campaign = headers.index('Campaign Name') + 1
    col_bc_id    = headers.index('Business Center ID of the identity') + 1
    col_video    = headers.index('Video Name') + 1
    col_text     = headers.index('Text') + 1
    col_url      = headers.index('Web URL') + 1
    col_ag       = headers.index('Ad Group Name') + 1

    base_bc_raw = ws_tmpl.cell(row=2, column=col_bc_id).value or ''
    single_id = base_bc_raw.split(',')[0].strip()

    # Collect template rows (row 2 onwards) as base structure
    tmpl_rows = []
    for row in ws_tmpl.iter_rows(min_row=2, values_only=False):
        country = row[col_ag - 1].value
        if not country:
            continue
        tmpl_rows.append({
            'country': country,
            'row_data': [cell.value for cell in row],
            'row_num': row[0].row,
        })

    # Create new workbook
    wb_out = openpyxl.load_workbook(TEMPLATE_PATH)
    ws_out = wb_out['Ads']

    # Clear all data rows
    for row in ws_out.iter_rows(min_row=2):
        for cell in row:
            cell.value = None

    today = datetime.now().strftime('%-d_%-m_%Y')
    out_row = 2

    for sku_entry in skus:
        sku = sku_entry.get('sku', '')
        brand = sku_entry.get('brand', '')
        video_names = sku_entry.get('videos', '')
        texts_by_lang = sku_entry.get('texts', {})
        urls_by_lang = sku_entry.get('urls', {})
        fallback_url = sku_entry.get('url') or sku_entry.get('source_url') or ''
        print(f"[master] SKU={sku} url={fallback_url!r} urls={urls_by_lang}")
        # Fallback: če urls prazen, uporabi url za vse jezike
        if not urls_by_lang and fallback_url:
            all_langs = list(set(list(COUNTRY_TO_LANG.values()) + ['sl','hr','rs','hu','cz','sk','pl','gr','ro','bg']))
            urls_by_lang = {lang: fallback_url for lang in all_langs}
        print(f"[master] SKU={sku} urls_by_lang keys={list(urls_by_lang.keys())[:5]}")

        videos = [v.strip() for v in re.findall(r'\[([^\]]+)\]', video_names)]
        new_bc_id = ','.join([single_id] * len(videos)) if videos else single_id
        new_campaign = f'[{brand}] Smart+ {sku} - {today}'

        for tmpl_row in tmpl_rows:
            country = tmpl_row['country']
            lang = COUNTRY_TO_LANG.get(country)

            # Preskoči RS če skip_rs
            skip_rs_master = sku_entry.get('skip_rs', False)
            if skip_rs_master and lang == 'rs':
                continue

            # Copy template row values
            orig_row = ws_tmpl[tmpl_row['row_num']]
            for col_idx, orig_cell in enumerate(orig_row, 1):
                ws_out.cell(row=out_row, column=col_idx).value = orig_cell.value

            # Fill in our data
            ws_out.cell(row=out_row, column=col_campaign).value = new_campaign
            ws_out.cell(row=out_row, column=col_bc_id).value = new_bc_id
            ws_out.cell(row=out_row, column=col_video).value = video_names
            if lang and lang in texts_by_lang:
                ws_out.cell(row=out_row, column=col_text).value = texts_by_lang[lang]
            # URL: lang-specifičen ali fallback
            url = (urls_by_lang.get(lang) if lang else None) or fallback_url or next(iter(urls_by_lang.values()), '')
            if url:
                ws_out.cell(row=out_row, column=col_url).value = url

            out_row += 1

    out_path = str(EXPORTS_DIR / f"master_{uuid.uuid4().hex[:8]}.xlsx")
    wb_out.save(out_path)
    return out_path


class MasterXlsxRequest(BaseModel):
    skus: List[dict]  # [{sku, brand, url, videos, texts, urls}]


@app.post("/build-master-xlsx")
async def build_master_xlsx_endpoint(req: MasterXlsxRequest):
    """Sestavi master XLS iz že shranjenih tekstov — brez API klicev."""
    skus_data = []
    for entry in req.skus:
        if not entry.get('videos'):
            continue
        skus_data.append({
            'sku':    entry.get('sku', ''),
            'brand':  entry.get('brand', ''),
            'videos': entry.get('videos', ''),
            'texts':  entry.get('texts', {}),
            'urls':   entry.get('urls', {}),
        })

    if not skus_data:
        return {"error": "Ni veljavnih SKU-jev (manjkajo video imena)."}

    try:
        path = build_master_xlsx(skus_data)
        return {"status": "ok", "file": path}
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.post("/generate-master-xlsx")
async def generate_master_xlsx(req: MasterXlsxRequest):
    await ensure_cache_fresh()

    skus_data = []
    for entry in req.skus:
        url = entry.get('url', '')
        sku = entry.get('sku', '')
        brand = entry.get('brand', '')
        videos = entry.get('videos', '')

        if not videos:
            continue  # preskoči SKU brez video imen

        # Generate TikTok texts
        user_msg = f"Preberi to stran in ustvari TikTok oglase: {url}"
        data = await generate_tiktok_one(user_msg, "url", url)
        if "error" in data:
            continue

        texts_by_lang = {lang: data[lang] for lang in ["sl","hr","rs","hu","cz","sk","pl","gr","ro","bg"] if lang in data}
        urls_by_lang = data.get("product_urls", {})

        skus_data.append({
            'sku': sku, 'brand': brand, 'videos': videos,
            'texts': texts_by_lang, 'urls': urls_by_lang
        })

        if len(skus_data) < len(req.skus):
            await asyncio.sleep(15)  # rate limit

    if not skus_data:
        return {"error": "Ni veljavnih SKU-jev za generiranje."}

    try:
        path = build_master_xlsx(skus_data)
        return {"status": "ok", "file": path}
    except FileNotFoundError as e:
        return {"error": str(e)}


    input: str
    mode: str
    pt_count: int = 1
    hl_count: int = 1
    source_url: Optional[str] = None
    qmode: str = "sonnet"


class MultiAdRequest(BaseModel):
    products: List[dict]
    pt_count: int = 1
    hl_count: int = 1
    qmode: str = "sonnet"


class TikTokRequest(BaseModel):
    source_url: str
    sku: str
    brand: str
    video_names: str
    skip_rs: bool = False


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/tiktok-history")
async def get_tiktok_history():
    if TT_HISTORY_FILE.exists():
        try:
            return json.loads(TT_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/tiktok-history")
async def save_tiktok_history(data: dict):
    try:
        history = data.get("history", [])
        TT_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(history)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/meta-history")
async def get_meta_history():
    if META_HISTORY_FILE.exists():
        try:
            return json.loads(META_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/meta-history")
async def save_meta_history(data: dict):
    try:
        history = data.get("history", [])
        META_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(history)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/forecast-entries")
async def get_forecast_entries():
    if FORECAST_ENTRIES_FILE.exists():
        try:
            return json.loads(FORECAST_ENTRIES_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

@app.post("/forecast-entries")
async def save_forecast_entries(data: dict):
    try:
        FORECAST_ENTRIES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/forecast-history")
async def get_forecast_history():
    if FORECAST_HISTORY_FILE.exists():
        try:
            return json.loads(FORECAST_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

@app.post("/forecast-history")
async def save_forecast_history(data: dict):
    try:
        FORECAST_HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/cache-status")
async def cache_status():
    return {"last_fetch": last_fetch.isoformat() if last_fetch else None,
            "stale": is_cache_stale(),
            "products_per_lang": {lang: len(p) for lang, p in feed_by_lang.items()},
            "slug_index_size": len(slug_to_id)}


@app.post("/refresh-cache")
async def refresh_cache():
    await fetch_all_feeds()
    return {"status": "ok", "last_fetch": last_fetch.isoformat()}


@app.post("/generate")
async def generate(req: AdRequest):
    await ensure_cache_fresh()
    user_msg = f"Preberi to stran in ustvari Meta oglase: {req.input}" if req.mode == "url" else f"Na podlagi tega opisa ustvari Meta oglase:\n\n{req.input}"
    return await generate_meta_one(user_msg, req.mode, req.source_url, req.pt_count, req.hl_count, req.qmode)


@app.post("/generate-multi")
async def generate_multi(req: MultiAdRequest):
    await ensure_cache_fresh()
    results = []
    for i, p in enumerate(req.products):
        url = p.get("url", "").strip()
        mode = p.get("mode", "url")
        if not url:
            results.append({"error": "Prazen URL"})
            continue
        user_msg = f"Preberi to stran in ustvari Meta oglase: {url}" if mode == "url" else f"Na podlagi tega opisa:\n\n{url}"
        result = await generate_meta_one(user_msg, mode, url if mode == "url" else None,
                                         req.pt_count, req.hl_count, req.qmode)
        results.append(result)
        if i < len(req.products) - 1:
            await asyncio.sleep(15)
    return {"results": results}


@app.post("/generate-multi-stream")
async def generate_multi_stream(req: MultiAdRequest):
    """SSE streaming endpoint — pošilja rezultate batch po batch."""
    await ensure_cache_fresh()

    async def event_stream():
        for i, p in enumerate(req.products):
            url = p.get("url", "").strip()
            mode = p.get("mode", "url")
            if not url:
                yield f"data: {json.dumps({'type': 'result', 'index': i, 'data': {'error': 'Prazen URL'}})}\n\n"
                continue

            # Notify frontend that this product is being processed
            yield f"data: {json.dumps({'type': 'loading', 'index': i, 'url': url})}\n\n"

            user_msg = f"Preberi to stran in ustvari Meta oglase: {url}" if mode == "url" else f"Na podlagi tega opisa:\n\n{url}"

            if req.qmode == "fast":
                # Step 1: SL generation
                yield f"data: {json.dumps({'type': 'progress', 'index': i, 'step': 'sl'})}\n\n"
                result = await generate_meta_sl_only(user_msg, mode, url if mode == "url" else None,
                                                      req.pt_count, req.hl_count)
                if "error" in result:
                    yield f"data: {json.dumps({'type': 'result', 'index': i, 'data': result})}\n\n"
                    if i < len(req.products) - 1:
                        await asyncio.sleep(15)
                    continue

                # Send SL immediately
                yield f"data: {json.dumps({'type': 'partial', 'index': i, 'langs': ['sl'], 'data': result})}\n\n"

                sl_pts = result["sl"]["pt"]
                sl_hls = result["sl"]["hl"]
                product_urls = result.get("product_urls", {})
                product_name = result.get("product", "Izdelek")

                # Step 2: Parallel translation in 4 batches of 2-3 langs
                pt_ph = ", ".join([f'"PT {i2+1}"' for i2 in range(req.pt_count)])
                hl_ph = ", ".join([f'"HL {i2+1}"' for i2 in range(req.hl_count)])

                lang_batches = [
                    ["hr", "rs"],
                    ["hu", "cz"],
                    ["sk", "pl"],
                    ["gr", "ro", "bg"],
                ]

                lang_info = {
                    "hr": "HR (hrvaščina, latinica)",
                    "rs": "RS (srbščina, SAMO latinica!)",
                    "hu": "HU (madžarščina - aglutinacijski jezik, ne prevajaj dobesedno)",
                    "cz": "CZ (češčina)",
                    "sk": "SK (slovaščina)",
                    "pl": "PL (poljščina)",
                    "gr": "GR (grščina, grška pisava!)",
                    "ro": "RO (romunščina, latinica)",
                    "bg": "BG (bolgarščina, SAMO cirilica!)",
                }

                full_result = {
                    "product": product_name,
                    "product_urls": product_urls,
                    "sl": {"pt": sl_pts, "hl": sl_hls},
                }

                for batch in lang_batches:
                    yield f"data: {json.dumps({'type': 'progress', 'index': i, 'step': 'translating', 'langs': batch})}\n\n"

                    batch_json_keys = ", ".join([
                        f'"{lang}":{{"pt":[{pt_ph}],"hl":[{hl_ph}]}}'
                        for lang in batch
                    ])
                    batch_lang_lines = "\n".join([f"- {lang_info[lang]}" for lang in batch])

                    batch_prompt = f"""Prevedi Meta oglase iz slovenščine v naslednje jezike. Ohrani ŠTEVILO in POZICIJO emoji-jev točno kot v originalu.

Primary Texts: {json.dumps(sl_pts, ensure_ascii=False)}
Headlines: {json.dumps(sl_hls, ensure_ascii=False)}

Prevedi SAMO v te jezike:
{batch_lang_lines}

SPLOŠNA PRAVILA:
- Ohrani prodajni/energičen ton
- Prevodi morajo zveneti kot materni govorec
- Ohrani ŠTEVILO emoji-jev
- Headlines: MAX 5 besed
- Ne prevajaj imen izdelkov/blagovnih znamk

Vrni SAMO JSON: {{{batch_json_keys}}}"""

                    batch_text = await call_claude(batch_prompt, "claude-haiku-4-5-20251001", None, 3000)
                    batch_data = parse_json_response(batch_text)

                    if batch_data:
                        full_result.update(batch_data)
                        yield f"data: {json.dumps({'type': 'partial', 'index': i, 'langs': batch, 'data': full_result})}\n\n"

                yield f"data: {json.dumps({'type': 'result', 'index': i, 'data': full_result})}\n\n"

            else:
                # Kreativni način — en klic, pošlji ko konča
                result = await generate_meta_one(user_msg, mode, url if mode == "url" else None,
                                                  req.pt_count, req.hl_count, req.qmode)
                yield f"data: {json.dumps({'type': 'result', 'index': i, 'data': result})}\n\n"

            if i < len(req.products) - 1:
                await asyncio.sleep(15)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/generate-tiktok")
async def generate_tiktok(req: TikTokRequest):
    await ensure_cache_fresh()
    user_msg = f"Preberi to stran in ustvari TikTok oglase: {req.source_url}"
    data = await generate_tiktok_one(user_msg, "url", req.source_url)
    if "error" in data:
        return data

    product_urls = data.get("product_urls", {})
    texts_by_lang = {lang: data[lang] for lang in ["sl","hr","rs","hu","cz","sk","pl","gr","ro","bg"] if lang in data}

    try:
        xlsx_path = build_tiktok_xlsx(
            sku=req.sku,
            brand=req.brand,
            video_names=req.video_names,
            texts_by_lang=texts_by_lang,
            urls_by_lang=product_urls,
            skip_rs=req.skip_rs
        )
        return {"status": "ok", "file": xlsx_path, "data": data}
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.post("/extract-videos")
async def extract_videos(data: dict):
    """Extract video filenames from a base64 screenshot using Claude vision."""
    image_b64 = data.get("image")
    media_type = data.get("media_type", "image/png")
    if not image_b64:
        return {"error": "Ni slike."}
    loop = asyncio.get_event_loop()
    msg = await loop.run_in_executor(None, lambda: client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": "Extract all video filenames from this screenshot. Return ONLY a JSON array of filenames, nothing else. Example: [\"VIDEO (1).mp4\", \"VIDEO (2).mp4\"]. Extract exactly as written, preserve spaces and capitalization."}
        ]}]
    ))
    text = msg.content[0].text.strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text).strip()
    try:
        filenames = json.loads(text)
        formatted = ",".join([f"[{f}]" for f in filenames])
        return {"filenames": filenames, "formatted": formatted}
    except json.JSONDecodeError:
        return {"error": "Ni uspelo prebrati imen. Poskusi znova z jasnejšo sliko."}


@app.get("/download/{filename}")
def download_file(filename: str):
    path = EXPORTS_DIR / filename
    if not path.exists():
        return {"error": "File not found"}
    return FileResponse(str(path), filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/kreative-history")
async def get_kreative_history():
    if KREATIVE_HISTORY_FILE.exists():
        try:
            return json.loads(KREATIVE_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/kreative-history")
async def save_kreative_history(data: dict):
    try:
        history = data.get("history", [])
        KREATIVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(history)}
    except Exception as e:
        return {"error": str(e)}


# ─── KREATIVE ENDPOINTS ───────────────────────────────────────────────────────

@app.post("/analyze-product-kreative")
async def analyze_product_kreative(data: dict):
    """Prebere stran izdelka in generira A/B/C opcije za kreative."""
    url = data.get("url", "").strip()
    if not url:
        return {"error": "Manjka URL."}

    # Fetch page
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as hc:
            resp = await hc.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text if resp.status_code == 200 else ""
    except Exception as e:
        return {"error": f"Ne morem prebrati strani: {e}"}


    # Build prompt for Claude to analyze product
    tools = [{"type": "web_search_20250305", "name": "web_search"}]
    analysis_prompt = f"""Preberi to spletno stran izdelka: {url}

Na podlagi opisa izdelka generiraj strukturirane podatke za kreative FB oglasov.

Vrni SAMO JSON (brez markdown) v tej obliki:
{{
  "name": "IME_IZDELKA_CAPS",
  "aOptions": [
    {{"label": "MAIN VERSION", "text": "benefit1, benefit2, benefit3"}},
    {{"label": "HIGH-CONVERT", "text": "benefit1, benefit2, benefit3"}},
    {{"label": "PROBLEM-SOLUTION", "text": "benefit1, benefit2, benefit3"}},
    {{"label": "ULTRA SIMPLE", "text": "benefit1, benefit2"}},
    {{"label": "SOCIAL PROOF", "text": "benefit1, benefit2, benefit3"}}
  ],
  "bOptions": [
    {{"label": "BEST", "text": "kratko ime vibeа ozadja"}},
    {{"label": "SECOND OPTION", "text": "kratko ime vibeа ozadja"}},
    {{"label": "SCROLL STOPPER", "text": "kratko ime vibeа ozadja"}},
    {{"label": "BONUS", "text": "kratko ime vibeа ozadja"}},
    {{"label": "LIFESTYLE", "text": "kratko ime vibeа ozadja"}}
  ]
}}

PRAVILA:
- name: samo ime blagovne znamke/modela z CAPS
- aOptions: PRODAJNI UDARCI (ne lastnosti!), max 2-3 besede vsak, v angleščini
- bOptions: KONCEPT/VIBE specifičen za TA izdelek, max 3 besede, vedno akcija ali moment
- VSE mora biti v angleščini
- Vrni točno 5 aOptions in 5 bOptions

PRIMERI (uči se iz teh vzorcev):

WEEDZAP (weed removal tool):
aOptions: "Pull the Root, Stop the Weed, No Chemicals" | "Weeds Gone, Root and All, One Tool" | "Weeds Keep Coming Back, Pull the Root, Done for Good" | "Twist, Pull, Gone"
bOptions: "root pull satisfying moment" | "no chemicals angle" | "before/after garden" | "no back pain angle"

ASHIRAFLUX (smokeless fire pit):
aOptions: "Real Flame, No Smoke, Anywhere You Are" | "No Fireplace? No Problem, Instant Cozy, Zero Smoke" | "Missing That Fire Feeling, Warm Vibes Instantly" | "Fill, Light, Relax"
bOptions: "evening atmosphere shot" | "smoke vs no smoke" | "first light moment" | "indoor safe angle"

STAXA (steel organizer shelf):
aOptions: "Double Your Space, Zero Clutter, Instant Order" | "Messy Counter, One Shelf, Problem Solved" | "No Room, Stack It Up, Space Created" | "Stack, Store, Done"
bOptions: "before/after counter" | "multi-room tour" | "satisfying load test" | "steel vs plastic"

SIZZELA (electric frying pan):
aOptions: "No Stove Needed, Cook Anywhere, Instant Heat" | "One Pan, Any Meal, Zero Hassle" | "No Stove, No Smoke, No Problem" | "Plug & Sizzle, Done"
bOptions: "sizzle sound moment" | "speed cooking demo" | "steam lid reveal" | "no stove freedom"

PLANTDRILL (garden auger):
aOptions: "Drill, Plant, Done, No Digging" | "One Bit, Perfect Holes, Zero Effort" | "Back-Breaking Digging, One Drill Bit, Done" | "Drill, Drop, Grow"
bOptions: "speed demo" | "planting demo" | "satisfying drill moment"

SMARTFITNESS (EMS stimulator):
aOptions: "Train Anywhere, No Gym, Real Results" | "On the Couch, Still Training, Zero Effort" | "No Time to Work Out, Wear It, Feel It Work" | "Stick, Activate, Tone"
bOptions: "lifestyle demo" | "before/after body" | "reaction moment"

SOWSYNC (seed spacing tool):
aOptions: "Plant Smart, Perfect Spacing, Grow Better" | "Even Rows, No Waste, Strong Growth" | "Messy Planting, Seed Tool, Better Yield" | "Place, Press, Plant"
bOptions: "before/after planting" | "planting demo" | "grid effect"

Sedaj generiraj za izdelek na tej strani po ISTEM vzorcu:"""

    text = await call_claude(analysis_prompt, "claude-sonnet-4-6", tools, 2000)
    result = parse_json_response(text)

    if not result:
        return {"error": "Ni uspelo analizirati izdelka. Poskusi znova."}

    return result


@app.post("/fetch-product-images")
async def fetch_product_images(data: dict):
    """Pobere slike izdelka s podane URL strani."""
    url = data.get("url", "").strip()
    if not url:
        return {"error": "Manjka URL."}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as hc:
            resp = await hc.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return {"error": f"Stran ni dostopna ({resp.status_code})."}
            html = resp.text

        # Extract img src attributes
        import re as _re
        srcs = _re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, _re.IGNORECASE)

        # Filter: only product-like images (skip icons, logos, tiny tracking pixels)
        from urllib.parse import urljoin
        base = url
        images = []
        seen = set()
        for src in srcs:
            if not src or src.startswith("data:"):
                continue
            full = urljoin(base, src)
            # Skip obviously non-product images
            skip_words = ["logo", "icon", "favicon", "sprite", "banner", "flag",
                         "payment", "badge", "star", "rating", "arrow", "tracking"]
            if any(w in full.lower() for w in skip_words):
                continue
            # Only jpg/png/webp
            if not any(ext in full.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                continue
            if full not in seen:
                seen.add(full)
                images.append(full)
            if len(images) >= 20:
                break

        return {"images": images, "count": len(images)}
    except Exception as e:
        return {"error": str(e)}


@app.post("/generate-kreative")
async def generate_kreative(data: dict):
    """Generira kreative z Google Gemini (Nano Banana 2) API."""
    import base64, struct, zlib

    product_name = data.get("productName", "")
    a_options = data.get("aOptions", [])
    b_options = data.get("bOptions", [])
    count = data.get("count", 4)
    ref_images = data.get("images", [])  # base64 data URLs

    if not product_name or not a_options or not b_options:
        return {"error": "Manjkajo podatki (ime izdelka, A ali B opcije)."}

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return {"error": "GEMINI_API_KEY ni nastavljen v Render environment variables."}

    # Build combinations
    combos = []
    for a in a_options:
        for b in b_options:
            prompt = (
                f"From these reference images create a new FB ad creative. "
                f"Try a more intense '{b.get('text', '')}' background. "
                f"Do not include any text/words on the image except the device name in capital letters '{product_name}' — place it where it fits best or makes sense. "
                f"If possible (if you recognize any suitable English naming styles), you can also create a logo from the name. "
                f"Highlight (can be through icons or text in English) that it is: {a.get('text', '')}. "
                f"Keep all text and icons well within the image borders — nothing should be cut off at the edges. Square 1:1 format."
            )
            combos.append({
                "combo": f"{a.get('label','A')} × {b.get('label','B')}",
                "prompt": prompt,
            })

    # Prepare reference image parts for Gemini
    # Upload referenčne slike enkrat na Gemini Files API (ne pošiljamo base64 v vsak klic)
    file_uris = []
    if ref_images:
        async with httpx.AsyncClient(timeout=60.0) as hc:
            for img_data in ref_images[:4]:  # max 4 referenčne slike
                try:
                    if "," in img_data:
                        header, b64 = img_data.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                    else:
                        b64 = img_data
                        mime = "image/jpeg"
                    img_bytes = __import__("base64").b64decode(b64)
                    upload_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={gemini_key}"
                    resp = await hc.post(
                        upload_url,
                        content=img_bytes,
                        headers={"Content-Type": mime, "X-Goog-Upload-Content-Type": mime,
                                 "X-Goog-Upload-Protocol": "raw"}
                    )
                    if resp.status_code == 200:
                        uri = resp.json().get("file", {}).get("uri", "")
                        if uri:
                            file_uris.append({"fileData": {"mimeType": mime, "fileUri": uri}})
                except Exception:
                    continue

    # Fallback: če Files API ne dela, uporabi inline za prvo sliko
    if file_uris:
        image_parts = file_uris
    elif ref_images:
        try:
            img_data = ref_images[0]
            if "," in img_data:
                header, b64 = img_data.split(",", 1)
                mime = header.split(":")[1].split(";")[0]
            else:
                b64 = img_data; mime = "image/jpeg"
            image_parts = [{"inline_data": {"mime_type": mime, "data": b64}}]
        except Exception:
            image_parts = []
    else:
        image_parts = []

    async def generate_one_image(combo_prompt, combo_label, idx):
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={gemini_key}"
        parts = list(image_parts) + [{"text": combo_prompt}]
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as hc:
                resp = await hc.post(api_url, json=payload, headers={"Content-Type": "application/json"})
                result = resp.json()
            if resp.status_code != 200:
                return None, result.get("error", {}).get("message", str(result))
            for candidate in result.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        inline = part["inlineData"]
                        mime = inline.get("mimeType", "image/png")
                        b64_data = inline.get("data", "")
                        return f"data:{mime};base64,{b64_data}", None
            return None, "Gemini ni vrnil slike: " + str(result)[:150]
        except Exception as e:
            return None, str(e)

    async def generate_combo(combo):
        """Generate `count` images for one combo in parallel."""
        tasks = [generate_one_image(combo["prompt"], combo["combo"], i) for i in range(count)]
        img_results = await asyncio.gather(*tasks)
        imgs = [img for img, err in img_results if img]
        errors = [err for img, err in img_results if err]
        if not imgs:
            return {"combo": combo["combo"], "images": [], "error": errors[0] if errors else "Ni slike"}
        return {"combo": combo["combo"], "images": imgs}

    # Vse kombinacije + vse slike vzporedno
    results = await asyncio.gather(*[generate_combo(combo) for combo in combos])
    return {"results": list(results)}


# ─── ASANA ENDPOINTS ──────────────────────────────────────────────────────────

ASANA_API = "https://app.asana.com/api/1.0"

def asana_headers():
    token = os.environ.get("ASANA_API_KEY", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

@app.get("/asana-search")
async def asana_search(q: str = ""):
    """Išče Asana taske po imenu."""
    if not q:
        return {"tasks": []}
    token = os.environ.get("ASANA_API_KEY", "")
    if not token:
        return {"error": "ASANA_API_KEY ni nastavljen."}
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            # Get workspaces first
            ws_resp = await hc.get(f"{ASANA_API}/workspaces", headers=asana_headers())
            workspaces = ws_resp.json().get("data", [])
            if not workspaces:
                return {"error": "Ni najdenih workspace-ov."}
            ws_gid = workspaces[0]["gid"]

            # Search tasks
            params = {"workspace": ws_gid, "text": q, "resource_type": "task",
                      "opt_fields": "gid,name,projects.name"}
            search_resp = await hc.get(f"{ASANA_API}/workspaces/{ws_gid}/tasks/search",
                                        params=params, headers=asana_headers())
            tasks_raw = search_resp.json().get("data", [])

            tasks = []
            for t in tasks_raw[:10]:
                projects = t.get("projects", [])
                proj_name = projects[0]["name"] if projects else ""
                tasks.append({"gid": t["gid"], "name": t["name"], "project": proj_name})

            return {"tasks": tasks}
    except Exception as e:
        return {"error": str(e)}


@app.post("/asana-attach")
async def asana_attach(data: dict):
    """Priloži slike (base64 data URLs) na Asana task."""
    task_id = data.get("task_id", "")
    image_urls = data.get("image_urls", [])

    if not task_id or not image_urls:
        return {"error": "Manjka task_id ali slike."}

    token = os.environ.get("ASANA_API_KEY", "")
    if not token:
        return {"error": "ASANA_API_KEY ni nastavljen."}

    attached = 0
    errors = []

    async with httpx.AsyncClient(timeout=60.0) as hc:
        for i, img_url in enumerate(image_urls):
            try:
                # Decode base64 data URL
                if img_url.startswith("data:"):
                    header, b64data = img_url.split(",", 1)
                    mime = header.split(":")[1].split(";")[0]
                    ext = mime.split("/")[1] if "/" in mime else "png"
                    img_bytes = __import__("base64").b64decode(b64data)
                else:
                    # Regular URL — fetch it
                    img_resp = await hc.get(img_url)
                    img_bytes = img_resp.content
                    mime = img_resp.headers.get("content-type", "image/png")
                    ext = "png"

                filename = f"kreativa_{i+1}.{ext}"

                # Upload to Asana as attachment
                files = {"file": (filename, img_bytes, mime)}
                attach_resp = await hc.post(
                    f"{ASANA_API}/tasks/{task_id}/attachments",
                    headers={"Authorization": f"Bearer {token}"},
                    files=files
                )

                if attach_resp.status_code in (200, 201):
                    attached += 1
                else:
                    errors.append(f"Slika {i+1}: {attach_resp.text[:100]}")

            except Exception as e:
                errors.append(f"Slika {i+1}: {str(e)}")

    return {"attached": attached, "errors": errors, "total": len(image_urls)}


# ─── LOKALIZACIJA ENDPOINT ───────────────────────────────────────────────────

LANG_NAMES = {
    "HR": "Croatian", "RS": "Serbian (Latin script)",
    "HU": "Hungarian", "CZ": "Czech", "SK": "Slovak",
    "PL": "Polish", "RO": "Romanian", "BG": "Bulgarian",
    "GR": "Greek", "SL": "Slovenian"
}

@app.post("/localize-kreativa")
async def localize_kreativa(data: dict):
    """Prevede tekst na hero kreativu v izbrane jezike z Gemini."""
    image_data = data.get("image", "") or (data.get("images", [None])[0] or "")
    images_data = data.get("images", [])
    if not images_data and image_data:
        images_data = [image_data]
    languages = data.get("languages", [])
    asana_task_id = data.get("asana_task_id")
    sku = data.get("sku", "SKU").strip().upper()
    brand = data.get("brand", "").strip()

    if not images_data or not languages:
        return {"error": "Manjka slika ali jeziki."}

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return {"error": "GEMINI_API_KEY ni nastavljen."}

    # Decode base64 image
    try:
        if "," in image_data:
            header, b64 = image_data.split(",", 1)
            mime = header.split(":")[1].split(";")[0]
        else:
            b64 = image_data
            mime = "image/jpeg"
    except Exception as e:
        return {"error": f"Napaka pri dekodiranju slike: {e}"}

    async def translate_one(lang_code, img_b64, img_mime, img_idx):
        lang_name = LANG_NAMES.get(lang_code, lang_code)
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={gemini_key}"
        brand_note = f" Do NOT translate these brand/product names (keep exactly as-is): {brand}." if brand else ""
        prompt = (
            f"Edit this image to translate all visible text into {lang_name}. "
            f"Keep EVERYTHING exactly the same — same people, same background, same layout, same design, same product, same icons, same colors, same fonts. "
            f"ONLY translate the text that is NOT a brand name or logo."
            f"{brand_note} "
            f"Do NOT translate or modify any brand names, logos, or product names. "
            f"Keep all text in the same position, same style, same size."
        )
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": img_mime, "data": img_b64}},
                {"text": prompt}
            ]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as hc:
                resp = await hc.post(api_url, json=payload, headers={"Content-Type": "application/json"})
                result = resp.json()
            if resp.status_code != 200:
                return {"lang": lang_code, "lang_name": lang_name, "url": None,
                        "error": result.get("error", {}).get("message", str(result))[:200]}
            for candidate in result.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        out_mime = part["inlineData"].get("mimeType", "image/png")
                        out_b64 = part["inlineData"].get("data", "")
                        img_url = f"data:{out_mime};base64,{out_b64}"
                        filename = f"{lang_code}{img_idx}_{sku}.png"
                        asana_ok = False
                        if asana_task_id:
                            try:
                                img_bytes = __import__("base64").b64decode(out_b64)
                                token = os.environ.get("ASANA_API_KEY", "")
                                async with httpx.AsyncClient(timeout=30.0) as hc2:
                                    attach_resp = await hc2.post(
                                        f"{ASANA_API}/tasks/{asana_task_id}/attachments",
                                        headers={"Authorization": f"Bearer {token}"},
                                        files={"file": (filename, img_bytes, out_mime)}
                                    )
                                asana_ok = attach_resp.status_code in (200, 201)
                            except Exception:
                                pass
                        return {"lang": lang_code, "lang_name": lang_name, "url": img_url, "filename": filename, "asana_ok": asana_ok}
            return {"lang": lang_code, "lang_name": lang_name, "url": None, "error": "Ni slike"}
        except Exception as e:
            return {"lang": lang_code, "lang_name": lang_name, "url": None, "error": str(e)}

    # Pripravi vse kombinacije slika × jezik vzporedno
    tasks = []
    for img_idx, img_data_item in enumerate(images_data, 1):
        try:
            if "," in img_data_item:
                header, b64 = img_data_item.split(",", 1)
                mime = header.split(":")[1].split(";")[0]
            else:
                b64 = img_data_item; mime = "image/jpeg"
        except Exception:
            continue
        for lang_code in languages:
            tasks.append(translate_one(lang_code, b64, mime, img_idx))
    results = await asyncio.gather(*tasks)
    return {"results": list(results)}


# ─── NAROČILNICE HISTORY ─────────────────────────────────────────────────────

NAROCILNICE_HISTORY_FILE = DATA_DIR / "narocilnice_history.json"

@app.get("/narocilnice-history")
async def get_narocilnice_history():
    if NAROCILNICE_HISTORY_FILE.exists():
        try:
            return json.loads(NAROCILNICE_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/narocilnice-history")
async def save_narocilnice_history(data: dict):
    try:
        history = []
        if NAROCILNICE_HISTORY_FILE.exists():
            try:
                history = json.loads(NAROCILNICE_HISTORY_FILE.read_text(encoding="utf-8"))
            except:
                history = []
        
        csv_text = data.get("csv", "")
        date = data.get("date", "")
        
        # Count negative rows
        rows = 0
        for line in csv_text.split('\n')[1:]:
            if line.strip():
                rows += 1
        
        history.append({"csv": csv_text, "date": date, "rows": rows})
        # Keep last 50
        if len(history) > 50:
            history = history[-50:]
        
        NAROCILNICE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(history)}
    except Exception as e:
        return {"error": str(e)}


# ─── NAROČILNICE SKU LOOKUP ───────────────────────────────────────────────────

@app.post("/narocilnice-lookup")
async def narocilnice_lookup(data: dict):
    """Poišče URL izdelka v Maaarket XML feedu po SKU ali nazivu."""
    skus = data.get("skus", [])  # list of {sku, naziv}
    
    await ensure_cache_fresh()
    
    results = {}
    sl_feed = feed_by_lang.get("sl", {})
    
    for item in skus:
        sku = item.get("sku", "").strip().upper()
        naziv = item.get("naziv", "").strip().lower()
        
        found_url = None
        
        # Search by SKU in title/id
        for g_id, prod in sl_feed.items():
            prod_title = prod.get("title", "").strip()
            prod_url = prod.get("url", "")
            prod_slug = extract_slug(prod_url) or ""
            
            # Match SKU in title or slug
            if (sku and (sku.lower() in prod_title.lower() or sku.lower() in prod_slug.lower())):
                found_url = prod_url
                break
        
        # Fallback: search by naziv words (first 3 significant words)
        if not found_url and naziv:
            words = [w for w in naziv.split() if len(w) > 3][:3]
            if words:
                best_score = 0
                for g_id, prod in sl_feed.items():
                    prod_title = prod.get("title", "").strip().lower()
                    score = sum(1 for w in words if w in prod_title)
                    if score > best_score and score >= 2:
                        best_score = score
                        found_url = prod.get("url", "")
        
        if found_url:
            results[sku] = found_url
    
    return {"urls": results}


@app.post("/narocilnice-history-set")
async def set_narocilnice_history(data: dict):
    """Nastavi celotno zgodovino (za brisanje)."""
    try:
        history = data.get("history", [])
        NAROCILNICE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(history)}
    except Exception as e:
        return {"error": str(e)}



# ─── FORECAST EOD (End-of-day končna naročila) ───────────────────────────────

FORECAST_EOD_FILE = DATA_DIR / "forecast_eod.json"

@app.get("/forecast-eod")
async def get_forecast_eod():
    if FORECAST_EOD_FILE.exists():
        try:
            return json.loads(FORECAST_EOD_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}

@app.post("/forecast-eod")
async def save_forecast_eod(data: dict):
    try:
        FORECAST_EOD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "count": len(data)}
    except Exception as e:
        return {"error": str(e)}


# ─── KARANTENA PDF PARSER ─────────────────────────────────────────────────────

from fastapi import UploadFile, File
import io
import re as _re

@app.post("/parse-karantena-pdf")
async def parse_karantena_pdf(file: UploadFile = File(...)):
    """Parsira PDF karantene in vrne strukturirane podatke."""
    try:
        import pdfplumber
        content = await file.read()
        rows = []
        
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            full_text = ""
            for page in pdf.pages:
                # Poskusi extract table najprej
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            if not row or not any(row):
                                continue
                            # Preskoči header vrstice
                            if row[0] and str(row[0]).strip().lower() in ('product_id', 'id', '#'):
                                continue
                            # Normalizacija vrstice
                            cells = [str(c).strip() if c else '' for c in row]
                            if len(cells) >= 3:
                                product_id = cells[0] if cells[0] else ''
                                sku = cells[1] if len(cells) > 1 else ''
                                title = cells[2] if len(cells) > 2 else ''
                                stock = cells[3] if len(cells) > 3 else '0'
                                stock_actual = cells[4] if len(cells) > 4 else '0'
                                position = cells[5] if len(cells) > 5 else ''
                                
                                # Preskoči header
                                if sku.lower() in ('product_sku', 'sku', ''):
                                    continue
                                
                                try: stock = int(float(stock))
                                except: stock = 0
                                try: stock_actual = int(float(stock_actual))
                                except: stock_actual = 0
                                
                                rows.append({
                                    'product_id': product_id,
                                    'sku': sku,
                                    'title': title,
                                    'stock': stock,
                                    'stock_actual': stock_actual,
                                    'position': position,
                                })
                else:
                    full_text += (page.extract_text() or "") + "\n"
            
            # Fallback: text parsing če ni tabel
            if not rows and full_text:
                lines = full_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 3 and parts[0].isdigit():
                        product_id = parts[0]
                        sku = parts[1]
                        # Preskoči header
                        if sku.lower() in ('product_sku', 'sku'):
                            continue
                        # Poišči zadnji del ki je številka (stock)
                        stock = 0
                        stock_actual = 0
                        position = ''
                        title_parts = []
                        for i, p in enumerate(parts[2:], 2):
                            if _re.match(r'^\d+$', p):
                                stock = int(p)
                                if i+1 < len(parts) and _re.match(r'^\d+$', parts[i+1]):
                                    stock_actual = int(parts[i+1])
                                    if i+2 < len(parts):
                                        position = parts[i+2]
                                break
                            else:
                                title_parts.append(p)
                        title = ' '.join(title_parts)
                        rows.append({
                            'product_id': product_id,
                            'sku': sku,
                            'title': title,
                            'stock': stock,
                            'stock_actual': stock_actual,
                            'position': position,
                        })
        
        if not rows:
            return {"error": "Ni podatkov v PDF-u."}
        
        print(f"[karantena] Parsed {len(rows)} rows from PDF")
        return {"rows": rows, "count": len(rows)}
        
    except ImportError:
        return {"error": "pdfplumber ni nameščen. Dodaj ga v requirements.txt."}
    except Exception as e:
        import traceback
        print(f"[karantena] Error: {e}\n{traceback.format_exc()[-500:]}")
        return {"error": str(e)}


# ─── KARANTENA HISTORY ────────────────────────────────────────────────────────

KARANTENA_HISTORY_FILE = DATA_DIR / "karantena_history.json"

@app.get("/karantena-history")
async def get_karantena_history():
    if KARANTENA_HISTORY_FILE.exists():
        try:
            return json.loads(KARANTENA_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/karantena-history")
async def save_karantena_history(data: dict):
    try:
        history = []
        if KARANTENA_HISTORY_FILE.exists():
            try:
                history = json.loads(KARANTENA_HISTORY_FILE.read_text(encoding="utf-8"))
            except:
                history = []
        history.append({
            "rows": data.get("rows", []),
            "filename": data.get("filename", ""),
            "date": data.get("date", "")
        })
        if len(history) > 30:
            history = history[-30:]
        KARANTENA_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/karantena-history-set")
async def set_karantena_history(data: dict):
    try:
        history = data.get("history", [])
        KARANTENA_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


# ─── VIDEO ADS — SCRIPT GENERATION ───────────────────────────────────────────

@app.post("/generate-video-scripts")
async def generate_video_scripts(data: dict):
    input_text = data.get("input", "").strip()
    duration = data.get("duration", 15)
    if not input_text:
        return {"error": "Manjka vnos."}

    mode = "url" if input_text.startswith("http") else "text"
    tools = [{"type": "web_search_20250305", "name": "web_search"}] if mode == "url" else []
    # ~2.5 besede/sekundo za naravni govorni tempo, -1s buffer
    words = max(20, min(120, int((duration - 1) * 2.5)))

    prompt = f"""{'Preberi to stran in' if mode == 'url' else 'Na podlagi tega opisa'} ustvari voice over skripte za video oglas v 10 jezikih.

{'Stran: ' + input_text if mode == 'url' else 'Opis: ' + input_text}

Pravila:
- Točno {words} besed na jezik (±5)
- Naravni govorni slog, kot da govori prijatelj
- Poudarek na eni glavni koristi izdelka
- Brez cen, brez "klikni", brez "naroči"
- Konec z močno izjavo (ne pozivom k akciji)
- SL: slovenščina, HR: hrvaščina (latinica), RS: srbščina (SAMO latinica), HU: madžarščina, CZ: češčina, SK: slovaščina, PL: poljščina, GR: grščina (grška pisava), RO: romunščina, BG: bolgarščina (SAMO cirilica)

Vrni SAMO JSON brez markdown:
{{"product": "ime izdelka", "sl": "...", "hr": "...", "rs": "...", "hu": "...", "cz": "...", "sk": "...", "pl": "...", "gr": "...", "ro": "...", "bg": "..."}}"""

    try:
        text = await call_claude(prompt, "claude-sonnet-4-6", tools if tools else None, 4000)
        data_parsed = parse_json_response(text)
        if not data_parsed:
            return {"error": "Napaka pri generiranju skript."}
        scripts = {k: v for k, v in data_parsed.items() if k != "product"}
        return {"scripts": scripts, "product": data_parsed.get("product", "")}
    except Exception as e:
        return {"error": str(e)}


# ─── VIDEO ADS — ELEVENLABS AUDIO ────────────────────────────────────────────

ELEVENLABS_VOICES = {
    "sl": "pNInz6obpgDQGcFmaJgB",  # Adam — multilingual
    "hr": "pNInz6obpgDQGcFmaJgB",
    "rs": "pNInz6obpgDQGcFmaJgB",
    "hu": "pNInz6obpgDQGcFmaJgB",
    "cz": "pNInz6obpgDQGcFmaJgB",
    "sk": "pNInz6obpgDQGcFmaJgB",
    "pl": "pNInz6obpgDQGcFmaJgB",
    "gr": "pNInz6obpgDQGcFmaJgB",
    "ro": "pNInz6obpgDQGcFmaJgB",
    "bg": "pNInz6obpgDQGcFmaJgB",
}

def _parse_words(alignment: dict):
    """Iz ElevenLabs alignment podatkov izloci seznam (beseda, start, end)."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    words = []
    cur_word, cur_start, cur_end = "", None, None
    for i, ch in enumerate(chars):
        if i >= len(starts):
            break
        t_start = starts[i]
        t_end = ends[i] if i < len(ends) else t_start + 0.1
        if ch in (' ', '\n', '\t'):
            if cur_word:
                words.append((cur_word, cur_start, cur_end))
            cur_word, cur_start, cur_end = "", None, None
        else:
            if cur_start is None:
                cur_start = t_start
            cur_end = t_end
            cur_word += ch
    if cur_word:
        words.append((cur_word, cur_start, cur_end))
    return words


def build_srt(alignment: dict) -> str:
    """Generira SRT iz ElevenLabs alignment (za download)."""
    words = _parse_words(alignment)
    if not words:
        return ""

    def fmt(s):
        h, m = int(s // 3600), int((s % 3600) // 60)
        sec, ms = int(s % 60), int((s - int(s)) * 1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    lines, i, idx = [], 0, 1
    while i < len(words):
        grp = [words[i]]
        i += 1
        while i < len(words) and len(grp) < 5 and (words[i][1] - grp[0][1]) < 3.0:
            grp.append(words[i]); i += 1
        lines.append(f"{idx}\n{fmt(grp[0][1])} --> {fmt(grp[-1][2])}\n{' '.join(w[0] for w in grp)}\n")
        idx += 1
    return "\n".join(lines)


def build_ass(alignment: dict) -> str:
    """Generira ASS karaoke podnapise — Stil B (bela+rumena, debela obroba)."""
    words = _parse_words(alignment)
    if not words:
        return ""

    # ASS header — Stil B: bela besedila, debela črna obroba, bold
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,52,&H00FFFFFF,&H00FFD600,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,20,20,80,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    def fmt(s):
        h, m = int(s // 3600), int((s % 3600) // 60)
        sec, cs = int(s % 60), int((s - int(s)) * 100)
        return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"

    # Grupiraj v vrstice (max 4 besede)
    lines_out = []
    i = 0
    while i < len(words):
        grp = [words[i]]; i += 1
        while i < len(words) and len(grp) < 4 and (words[i][1] - grp[0][1]) < 2.5:
            grp.append(words[i]); i += 1

        t_in = grp[0][1]
        t_out = grp[-1][2] + 0.05

        # Karaoke: vsaka beseda dobi {\kXX} tag (čas v centisekundah)
        parts = []
        for wi, (word, wstart, wend) in enumerate(grp):
            # Čas do naslednje besede ali konec
            if wi + 1 < len(grp):
                dur_cs = int((grp[wi+1][1] - wstart) * 100)
            else:
                dur_cs = int((wend - wstart) * 100) + 5
            dur_cs = max(dur_cs, 5)
            parts.append("{" + chr(92) + "k" + str(dur_cs) + "}" + word)

        karaoke_text = " ".join(parts)
        lines_out.append(f"Dialogue: 0,{fmt(t_in)},{fmt(t_out)},Default,,0,0,0,,{karaoke_text}")

    return header + "\n".join(lines_out)


@app.post("/generate-audio")
async def generate_audio(data: dict):
    text = data.get("text", "").strip()
    lang = data.get("lang", "sl")
    if not text:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Manjka tekst."}, status_code=400)

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "ELEVENLABS_API_KEY ni nastavljen."}, status_code=400)

    voice_id = ELEVENLABS_VOICES.get(lang, "pNInz6obpgDQGcFmaJgB")

    try:
        async with httpx.AsyncClient(timeout=60.0) as hc:
            # Uporabi /with-timestamps endpoint za alignment podatke
            resp = await hc.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
            )

        if resp.status_code != 200:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": f"ElevenLabs napaka {resp.status_code}: {resp.text[:300]}"}, status_code=400)

        result = resp.json()
        
        # Dekodira audio iz base64
        import base64
        audio_b64 = result.get("audio_base64", "")
        audio_bytes = base64.b64decode(audio_b64)
        
        # Generiraj SRT (za download) in ASS (za karaoke merge)
        alignment = result.get("alignment", {})
        srt = build_srt(alignment)
        ass = build_ass(alignment)

        return {
            "audio_base64": audio_b64,
            "srt": srt,
            "ass": ass,
            "lang": lang
        }

    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── MERGE VIDEO + AUDIO ──────────────────────────────────────────────────────

@app.post("/merge-video-audio")
async def merge_video_audio(
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    lang: str = "sl",
    srt: UploadFile = File(None),
):
    """Spoji video + audio (+ opcijsko SRT podnapisi) z FFmpeg."""
    import subprocess, tempfile
    from fastapi.responses import JSONResponse as JR
    # Uporabi static-ffmpeg da dobimo ffmpeg binarko brez root
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    try:
        with tempfile.TemporaryDirectory() as tmp:
            video_path = f"{tmp}/input.mp4"
            audio_path = f"{tmp}/audio.mp3"
            srt_path = f"{tmp}/subs.srt"
            ass_path = f"{tmp}/subs.ass"
            output_path = f"{tmp}/output_{lang}.mp4"

            with open(video_path, "wb") as f:
                f.write(await video.read())
            with open(audio_path, "wb") as f:
                f.write(await audio.read())

            has_srt = False
            if srt:
                srt_content = await srt.read()
                if srt_content.strip():
                    with open(srt_path, "wb") as f:
                        f.write(srt_content)
                    # Poskusi parsati kot ASS (začne z [Script Info])
                    if srt_content.startswith(b'[Script Info]'):
                        with open(ass_path, "wb") as f:
                            f.write(srt_content)
                        has_srt = 'ass'
                    else:
                        has_srt = 'srt' 

            if has_srt:
                # ASS karaoke ali SRT fallback
                sub_file = ass_path if has_srt == 'ass' else srt_path
                if has_srt == 'ass':
                    vf = f"ass={sub_file}"
                else:
                    vf = f"subtitles={sub_file}:force_style='FontName=Arial,FontSize=52,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=4,Bold=1,Alignment=2,MarginV=80'"
                cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-i", audio_path,
                    "-vf", vf,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-shortest",
                    output_path
                ]
            else:
                # Samo audio zamenjava, video brez rekodiranja
                cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-i", audio_path,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path
                ]

            result = subprocess.run(cmd, capture_output=True, timeout=180)

            if result.returncode != 0:
                err_msg = result.stderr.decode(errors='replace')[-400:]
                print(f"[merge] FFmpeg error: {err_msg}")
                return JR({"error": f"FFmpeg napaka: {err_msg}"}, status_code=500)

            with open(output_path, "rb") as f:
                video_bytes = f.read()

            return StreamingResponse(
                iter([video_bytes]),
                media_type="video/mp4",
                headers={"Content-Disposition": f"attachment; filename=video_{lang}.mp4"}
            )
    except subprocess.TimeoutExpired:
        return JR({"error": "FFmpeg timeout."}, status_code=500)
    except Exception as e:
        return JR({"error": str(e)}, status_code=500)


# ─── VIDEO ADS HISTORY ────────────────────────────────────────────────────────

VADS_HISTORY_FILE = DATA_DIR / "vads_history.json"

def vads_cleanup_old():
    """Zbriše vnose starejše od 7 dni."""
    if not VADS_HISTORY_FILE.exists():
        return
    try:
        history = json.loads(VADS_HISTORY_FILE.read_text(encoding="utf-8"))
        cutoff = datetime.now() - timedelta(days=7)
        history = [h for h in history if datetime.strptime(h.get("date","1.1.2000 00:00"), "%d.%m.%Y %H:%M") > cutoff]
        VADS_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass

@app.get("/vads-history")
async def get_vads_history():
    vads_cleanup_old()
    if VADS_HISTORY_FILE.exists():
        try:
            return json.loads(VADS_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

@app.post("/vads-history")
async def save_vads_history(data: dict):
    try:
        history = []
        if VADS_HISTORY_FILE.exists():
            try:
                history = json.loads(VADS_HISTORY_FILE.read_text(encoding="utf-8"))
            except:
                history = []
        history.append({
            "input": data.get("input", ""),
            "product": data.get("product", ""),
            "scripts": data.get("scripts", {}),
            "date": data.get("date", "")
        })
        if len(history) > 50:
            history = history[-50:]
        VADS_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/vads-history-set")
async def set_vads_history(data: dict):
    try:
        history = data.get("history", [])
        VADS_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}
