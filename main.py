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

Vrni SAMO JSON brez markdown, brez uvodnega besedila — vrednosti so že zformatirana TikTok vrednost z oglatimi oklepaji:
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
}}
POMEMBNO: Začni direktno z {{ in končaj z }} — nobenih dodatnih besed pred ali po JSON."""


# ─── GENERATE HELPERS ────────────────────────────────────────────────────────

def parse_json_response(text: str) -> Optional[dict]:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text).strip()
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
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
                      texts_by_lang: dict, urls_by_lang: dict) -> str:
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

    for row in ws.iter_rows(min_row=2):
        r = row[0].row
        country = ws.cell(row=r, column=col_ag).value
        if not country:
            continue
        lang = COUNTRY_TO_LANG.get(country)
        ws.cell(row=r, column=col_campaign).value = new_campaign
        ws.cell(row=r, column=col_bc_id).value = new_bc_id
        ws.cell(row=r, column=col_video).value = video_names
        if lang and lang in texts_by_lang:
            ws.cell(row=r, column=col_text).value = texts_by_lang[lang]
        if lang and lang in urls_by_lang:
            ws.cell(row=r, column=col_url).value = urls_by_lang[lang]

    out_path = str(EXPORTS_DIR / f"tiktok_{sku}_{uuid.uuid4().hex[:8]}.xlsx")
    wb.save(out_path)
    return out_path


# ─── MODELS ──────────────────────────────────────────────────────────────────

class AdRequest(BaseModel):
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
            urls_by_lang=product_urls
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
