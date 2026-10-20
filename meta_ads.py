# 📘 Meta Ads (Beta) — SKU → 1 kampanja (vsi trgi naenkrat), ad set = trg, oglasi = 5 lokaliziranih Flare kreativ + univerzalni videi
# (2026-10-15). Tok (čarovnik): 1) koncept: A/B opcije kot generator Kreative (/analyze-product-kreative) + SLO HL/PT + videi iz Asane
# → 2) 5 angleških kreativ z ISTIM promptom in Flare kot generator Kreative → 3) lokalizacija: HL/PT v jezike trgov (Sonnet) + prevod
# angleških napisov na sliki s promptom »Lok« (/localize-kreativa; NB2.1 privzeto ali Flare) → pregled kot FB oglas → CSV za Ads Manager »Import ads« (UTF-16 TAB, stolpci Metinega
# izvoza; preizkušeno 2026-10-15: 12/12 oglasov) + slike/ + videi/ (ujemanje po imenu datoteke). Oglasi z več naslovi/besedili
# (Flexible) se ne uvozijo → 1 oglas = 1 kreativa + 1 Title + 1 Body. Ločen modul, vklop: meta_ads.vklopi(globals()).
import asyncio
import base64
import csv
import io
import json
import random
import re
import uuid
import zipfile
from datetime import datetime, timedelta

MA_TRGI = ["sl", "hr", "rs", "hu", "pl", "cz", "sk", "gr", "bg", "ro"]
MA_JEZIK = {"sl": "Slovenian", "hr": "Croatian", "rs": "Serbian (Latin script, never Cyrillic)", "hu": "Hungarian", "pl": "Polish",
            "cz": "Czech", "sk": "Slovak", "gr": "Greek (Greek alphabet)", "bg": "Bulgarian (Cyrillic)", "ro": "Romanian"}
MA_JEZIK_SL = {"sl": "slovenščina", "hr": "hrvaščina", "rs": "srbščina (latinica)", "hu": "madžarščina", "pl": "poljščina", "cz": "češčina",
               "sk": "slovaščina", "gr": "grščina", "bg": "bolgarščina", "ro": "romunščina"}
MA_DRZAVA = {"sl": "SI", "hr": "HR", "rs": "RS", "hu": "HU", "pl": "PL", "cz": "CZ", "sk": "SK", "gr": "GR", "bg": "BG", "ro": "RO"}
MA_PIKSEL = {"sl": "824813018035664", "pl": "594485055250881", "sk": "776399419706604", "hr": "208841773552108", "rs": "267002177947845",
             "ro": "425303159069154", "bg": "5475417162514514", "hu": "317577872660835", "cz": "834090430851647", "gr": "3179900732285651"}
# FB strani (limit 250 oglasov / stran) → IG račun; ig_x = ID IG računa, kot ga kaže Ads Manager (stolpec »Instagram Account ID« z x:) —
# novi 1784… v »Instagram Account ID (New)« Meta ob uvozu NE upošteva (2026-10-17: vsi oglasi dobili napačen IG); manjka še Retail
MA_STRANI = {
    "101449685670882": {"ime": "Maaarket EU", "ig": "17841450081366206", "ig_x": "4839343202764200"},
    "113166093926419": {"ime": "Maaarket Europe", "ig": "17841444633130037", "ig_x": "5158852410822242"},
    "103042431541052": {"ime": "Maaarket", "ig": "17841441158665910", "ig_x": "3134992383245025"},
    "100174912815985": {"ime": "Maaarket Store", "ig": "17841464785772189", "ig_x": "7143299575791040"},
    "100158825529238": {"ime": "Maaarket PL", "ig": "17841447422595264", "ig_x": "4501245506558690"},
    "108850387978565": {"ime": "Maaarket Sk", "ig": "17841446949811305", "ig_x": "3764584170306401"},
    "105709857728802": {"ime": "Maaarket Hr", "ig": "17841436577490293", "ig_x": "3912646375476521"},
    "111891964957486": {"ime": "Maaarket Retail", "ig": "17841451744798020"},
    "100747945468598": {"ime": "Maaarket Cz", "ig": "17841447402045875", "ig_x": "4007613509295987"},
    "107310948408390": {"ime": "Maaarket Outlet", "ig": "17841450415404322", "ig_x": "4484961918278211"},
}
# privzeta stran po trgu (strani trga + splošne razporejene, da noben ne preseže 250 oglasov); v koraku 3 jo lahko zamenjaš
MA_STRAN_TRG = {"pl": "100158825529238", "sk": "108850387978565", "hr": "105709857728802", "cz": "100747945468598", "sl": "101449685670882",
                "rs": "107310948408390", "hu": "111891964957486", "gr": "113166093926419", "bg": "103042431541052", "ro": "100174912815985"}
MA_CTA = {"sl": "Kupi zdaj", "hr": "Kupi sada", "rs": "Kupi sada", "hu": "Vásárolj most", "pl": "Kup teraz", "cz": "Koupit",
          "sk": "Kúpiť teraz", "gr": "Αγόρασε τώρα", "bg": "Купи сега", "ro": "Cumpără acum"}   # samo za predogled (CTA = SHOP_NOW)
MA_EMOJI = "✅ ⭐ 🔥 💪 🎯 👍 ❤️ 💥 🚀 ✨ 💡 🎁 💰 👌 🙌 😍 💎 🏆 ⚡ 🌟 👏 💫 🛒 📦 🔑 💯 😊 🤩 🌿 🌱 🍃 🌸 🌻 🌞 🍀 🎉 🎊 🛍️ 💚 💙 🧡 💜 🤍 🖤"
# Bid cap po trgu (€, kot v tekočih kampanjah 2026-10-16) — v koraku 3 nastavljiv po trgu
MA_BID = {"pl": 7.7, "bg": 7.7, "gr": 7.7, "cz": 7.7, "ro": 8.5, "rs": 9.0, "sk": 9.0, "hu": 9.0, "sl": 9.0, "hr": 9.0}
MA_ADSET = {"sl": "SLO"}   # ime ad seta (ostali = koda trga)
# 🎬 5 različnih tipov scene + postavitev napisov (2026-10-16: vseh 5 kreativ je bilo videti enako — ista referenca, isti kot, ista postavitev)
MA_SCENE = {
    "hero": {"ime": "Hero izdelek", "vloga": "packshot",
             "scena": "HERO PRODUCT SHOT: the product large and centred as the star of the image in a premium staged setting, dramatic lighting, shallow depth of field.",
             "postavitev": "hook headline across the top, the 3 benefit icons in a row along the bottom, small logo in the bottom-right corner."},
    "uporaba": {"ime": "V uporabi", "vloga": "uporaba",
                "scena": "IN USE: a close-up of a real person's hands using the product exactly as intended, showing the action; the product clearly visible and recognisable.",
                "postavitev": "hook headline on the LEFT side stacked in 2–3 lines, the 3 benefit icons stacked vertically on the RIGHT side, small logo in the top-right corner."},
    "prej_potem": {"ime": "Prej / potem", "vloga": "prej_potem",
                   "scena": "BEFORE / AFTER: split composition — one side shows the problem (before), the other side shows the result achieved with the product (after), with a clean dividing line; small 'BEFORE' and 'AFTER' labels are allowed.",
                   "postavitev": "hook headline across the top above the split, the 3 benefit icons in a row along the bottom, small logo in the top-left corner."},
    "okolje": {"ime": "Okolje / lifestyle", "vloga": "okolje",
               "scena": "LIFESTYLE: a wide, emotional scene of the product in its real environment with people enjoying the result, warm natural light, authentic and aspirational.",
               "postavitev": "hook headline at the BOTTOM over a soft dark gradient, the 3 benefit icons in a row just above it, small logo in the top-left corner."},
    "detajl": {"ime": "Detajl / komplet", "vloga": "detajl",
               "scena": "DETAIL / BUNDLE: a macro close-up of the product's key feature or the complete set neatly arranged, rich textures, crisp studio light.",
               "postavitev": "hook headline in the top-left area, the 3 benefits as badges in a vertical column on the LEFT, small logo in the bottom-right corner."},
    "eksperiment": {"ime": "🧪 Eksperiment", "vloga": "packshot", "scena": "", "postavitev": ""},   # smer naključno iz MA_EKSPERIMENTI ob vsakem risanju
}
# 🧪 kreativa 5 = eksperiment (2026-10-18): ob vsakem risanju / ↻ druga drzna umetniška smer — testira nove smeri, ki jih sicer ne bi
MA_EKSPERIMENTI = [
    "BOLD COLOUR BLOCK: flat, saturated graphic background in 2–3 strong colours, the product cut out and large, modern poster style.",
    "3D FLOATING: the product floating in mid-air with its key parts or effects (water, sparks, light, motion trails) exploding around it, hyper-real 3D render look.",
    "SURREAL: an unexpected, surreal oversized scene that dramatises the main benefit (e.g. the product as a giant hero object in a miniature world).",
    "EXTREME ANGLE: very unusual camera angle (top-down flat lay or worm's-eye view) with dramatic perspective and strong shadows.",
    "POP-ART / COMIC: pop-art or comic-book style background with halftone dots and bold outlines, the product itself kept photorealistic.",
    "ONE-FRAME BEFORE/AFTER: one continuous image where the left half shows the frustrating problem and the right half the perfect result, with a bold diagonal split.",
    "MINIMAL LUXURY: ultra-minimal premium composition, lots of negative space, soft gradient light, the product like a luxury object on a pedestal.",
    "NEON NIGHT: dark night scene with neon glow and reflections, cinematic and high contrast, the product lit like a hero.",
]
MA_SCENE_RED = ["hero", "uporaba", "prej_potem", "okolje", "eksperiment"]   # kreativa 1–5 (detajl/komplet ostane na izbiro)
MA_ZNAK = "🤖"   # znak pred imenom kampanje = ustvarjeno v suban.ai
MA_SLIKA = {"1:1": (1080, 1080), "4:5": (1080, 1350)}   # 1:1 kot generator Kreative; 4:5 = preizkus za mobilni Feed (privzeto kreativa 5)
MA_FLARE_SIZE = {"1:1": "1024x1024", "4:5": "1024x1536"}   # 4:5: Flare 2:3 → izrez sredine 4:5
MA_N_KREATIV = 5
# stalni stolpci iz vzorčne kampanje DERISILK (izvoz 2026-10-15) — vse ostalo prazno
MA_STALNO = {
    "Campaign Objective": "Outcome Sales", "Buying Type": "AUCTION", "Campaign Bid Strategy": "Bid cap", "New Objective": "Yes",
    "Buy With Prime Type": "NONE", "Is Budget Scheduling Enabled For Campaign": "No", "Campaign High Demand Periods": "[]",
    "Buy With Integration Partner": "NONE", "Destination Type": "UNDEFINED", "Use Accelerated Delivery": "No",
    "Is Budget Scheduling Enabled For Ad Set": "No", "Ad Set High Demand Periods": "[]", "Optimized Event": "PURCHASE",
    "Location Types": "frequently_in, home, recent", "Age Min": "18", "Age Max": "65", "Advantage Audience": "1",
    "Targeting Optimization": "expansion_all", "Beneficiary": "Suban d.o.o.", "Payer": "Suban d.o.o.",
    "Brand Safety Inventory Filtering Levels": "FACEBOOK_STANDARD, AN_STANDARD", "Optimization Goal": "OFFSITE_CONVERSIONS",
    "Attribution Spec": '[{"event_type":"CLICK_THROUGH","window_days":1}]', "Billing Event": "IMPRESSIONS",
    "Regional Regulated Categories": "VOLUNTARY_VERIFICATION", "Optimize text per person": "No", "Optimized Ad Creative": "No",
    "Call to Action": "SHOP_NOW", "Additional Custom Tracking Specs": "[]", "Video Retargeting": "No", "Use Page as Actor": "No",
    "Degrees of Freedom Type": "USER_ENROLLED_AUTOFLOW",
}
MA_GLAVE_FILE = "meta_ads_glave.json"   # 422 stolpcev Metinega izvoza (v repozitoriju, static/)


def vklopi(G: dict):
    app, DATA_DIR = G["app"], G["DATA_DIR"]
    _jload, _jsave, _lj_iso = G["_jload"], G["_jsave"], G["_lj_iso"]
    from fastapi import Request
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

    PAK_FILE = DATA_DIR / "meta_ads_paketi.json"   # {paketi: [...] (zadnjih 30), evidenca: [...], brez_rs: [SKU]}
    MAPA = DATA_DIR / "meta_ads"
    lock = asyncio.Lock()
    flare_sem = asyncio.Semaphore(4)
    try:
        GLAVE = json.load(open("static/" + MA_GLAVE_FILE, encoding="utf-8"))
    except Exception as e:
        GLAVE = []
        print(f"[meta-ads] glave CSV: {e}")

    def prijava(request) -> bool:
        return G["_auth_check_token"](request.cookies.get(G["AUTH_COOKIE"], ""))

    def ni():
        return JSONResponse({"ok": False, "error": "Prijavi se."}, status_code=403)

    def nalozi():
        d = _jload(PAK_FILE, {}) or {}
        d.setdefault("paketi", []); d.setdefault("evidenca", []); d.setdefault("brez_rs", [])
        return d

    async def pak_set(pid, fn):
        async with lock:
            d = nalozi()
            p = next((x for x in d["paketi"] if x["id"] == pid), None)
            if p is not None:
                fn(p)
                _jsave(PAK_FILE, d)

    def pak_get(pid):
        return next((x for x in nalozi()["paketi"] if x["id"] == pid), None)

    def claude_json(prompt, max_tokens=8000):
        msg = G["client"].messages.create(model="claude-sonnet-4-6", max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        raw = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        return beri_json(raw)

    def beri_json(raw):
        """Prvi veljaven JSON objekt v odgovoru (model včasih doda besedilo ali drug {…} za JSON → »Extra data«)."""
        dec = json.JSONDecoder()
        najboljsi = {}
        for m in re.finditer(r"\{", raw or ""):
            try:
                obj, _ = dec.raw_decode(raw, m.start())
            except ValueError:
                continue
            if isinstance(obj, dict) and len(json.dumps(obj)) > len(json.dumps(najboljsi)):
                najboljsi = obj   # največji objekt (ne gnezden delček)
        return najboljsi

    def najdi(rows, sku):
        u = sku.strip().upper()
        for r in rows:
            if (r.get("sku") or "").upper() == u or (r.get("nc_sku") or "").upper() == u:
                return r
        for r in rows:
            if u in re.split(r"[-/\s]+", (r.get("sku") or "").upper()):
                return r
        return None

    async def izdelek_po_trgih(sku):
        """{trg: {url, g_id, naziv}} iz Marže trga + RS neuvoz (🚫)."""
        neuvoz = (_jload(DATA_DIR / "marza_ne_uvazamo.json", {}) or {})
        out = {}

        async def en(t):
            try:
                res = await G["_marza_trgi_get"](t)
                r = najdi((res or {}).get("rows") or [], sku)
            except Exception as e:
                print(f"[meta-ads] marža {t}: {e}")
                r = None
            if r:
                out[t] = {"url": r.get("url") or "", "g_id": str(r.get("g_id") or ""), "naziv": r.get("naziv") or "",
                          "cms_id": str(r.get("cms_id") or ""), "slika": r.get("slika") or "",
                          "neuvoz": str(r.get("g_id") or "") in (neuvoz.get(t) or {})}
        await asyncio.gather(*(en(t) for t in MA_TRGI))
        return out

    # ── Flare / NB2.1 ──
    async def flare(refs, prompt, razmerje="1:1", funkcija="meta_ads", n_ref=1):
        """refs = [(bytes, mime)] → GPT Image 2.5 Flare 1024×1024 (kot generator Kreative) → 1080×1080 (jpeg)."""
        import httpx, os
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY ni nastavljen")
        files = [("image[]", (f"ref{i}.{m.split('/')[-1]}", b, m)) for i, (b, m) in enumerate(refs[:n_ref])]   # kreative: do 3 (packshot + slika scene), prevod: 1
        form = {"model": "gpt-image-2.5-flare", "prompt": prompt, "size": MA_FLARE_SIZE.get(razmerje, "1024x1024"), "n": "1", "output_format": "jpeg"}
        async with flare_sem:
            async with httpx.AsyncClient(timeout=300) as hc:
                r = await hc.post("https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {key}"}, data=form, files=files)
                j = r.json()
        if r.status_code != 200:
            raise RuntimeError("Flare: " + str((j.get("error") or {}).get("message") or j)[:200])
        try:
            G["_ai_log_openai_img"]("gpt-image-2.5-flare", j, funkcija)
        except Exception:
            pass
        b64 = ((j.get("data") or [{}])[0]).get("b64_json")
        if not b64:
            raise RuntimeError("Flare ni vrnil slike")
        return await asyncio.to_thread(obrez, base64.b64decode(b64), razmerje)

    async def nb21(ref, prompt, razmerje="1:1"):
        """NB2.1 (Gemini) urejanje osnovne slike — alternativa Flare za besedilo na sliki."""
        import httpx, os
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY ni nastavljen")
        modeli = [G.get("GEMINI_FLASH_IMG") or "gemini-nano-banana-2.1"] + ([G["GEMINI_FLASH_IMG_STARI"]] if G.get("GEMINI_FLASH_IMG_STARI") else [])
        parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(ref).decode()}}, {"text": prompt}]
        zadnja = ""
        async with flare_sem:
            async with httpx.AsyncClient(timeout=180) as hc:
                for model in modeli:
                    r = await hc.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                                      json={"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": razmerje}}})
                    j = r.json()
                    if r.status_code != 200:
                        zadnja = str((j.get("error") or {}).get("message") or j)[:200]; continue
                    try:
                        G["_ai_log_gemini"](model, j, "meta_ads")
                    except Exception:
                        pass
                    for c in j.get("candidates") or []:
                        for pt in (c.get("content") or {}).get("parts") or []:
                            if "inlineData" in pt:
                                return await asyncio.to_thread(obrez, base64.b64decode(pt["inlineData"].get("data") or ""), razmerje)
                    zadnja = "NB2.1 ni vrnil slike"
        raise RuntimeError(zadnja or "napaka NB2.1")

    def obrez(raw, razmerje="1:1"):
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = MA_SLIKA.get(razmerje, MA_SLIKA["1:1"])
        r0, r1 = im.width / im.height, w / h
        if r0 > r1 + 0.01:
            nw = int(im.height * r1); x = (im.width - nw) // 2; im = im.crop((x, 0, x + nw, im.height))
        elif r0 < r1 - 0.01:
            nh = int(im.width / r1); y = (im.height - nh) // 2; im = im.crop((0, y, im.width, y + nh))
        im = im.resize((w, h))
        b = io.BytesIO(); im.save(b, format="JPEG", quality=90); return b.getvalue()

    def kvadrat_45_platno(raw):
        """1:1 kreativa → 1080×1350: kreativa na sredini (1080×1080), pasova 135 px zgoraj/spodaj = zamegljen podaljšek robov."""
        from PIL import Image, ImageFilter
        im = Image.open(io.BytesIO(raw)).convert("RGB").resize((1080, 1080))
        c = Image.new("RGB", (1080, 1350))
        c.paste(im.crop((0, 0, 1080, 40)).resize((1080, 135)).filter(ImageFilter.GaussianBlur(14)), (0, 0))
        c.paste(im.crop((0, 1040, 1080, 1080)).resize((1080, 135)).filter(ImageFilter.GaussianBlur(14)), (0, 1215))
        c.paste(im, (0, 135))
        b = io.BytesIO(); c.save(b, format="JPEG", quality=92); return b.getvalue(), im

    async def kvadrat_v_45(raw):
        """Varna 4:5: kvadrat na sredini + NB2.1 podaljša SAMO ozadje v pasova; sredino nato vedno vrnemo iz izvirnika (AI je ne sme spremeniti).
        Ob napaki AI ostane zamegljen podaljšek — vse pomembno je vedno v osrednjem kvadratu (varno tudi za FB obrez na 1:1)."""
        platno, kv = await asyncio.to_thread(kvadrat_45_platno, raw)
        try:
            ai = await nb21(platno, "This image has a finished square ad creative in the middle and blurry placeholder bands at the top and bottom. "
                                    "Replace ONLY the blurry top and bottom bands with a natural, seamless continuation of the background scene "
                                    "(sky, wall, table, floor — matching light and colours). Do NOT add any text, letters, icons, logos or product parts in the bands. "
                                    "Do NOT change anything in the central square.", "4:5")

            def zlepi(a):
                from PIL import Image
                im = Image.open(io.BytesIO(a)).convert("RGB").resize((1080, 1350))
                im.paste(kv, (0, 135))   # sredina = izvirna kreativa (napisi ostanejo točno taki)
                b = io.BytesIO(); im.save(b, format="JPEG", quality=90); return b.getvalue()
            return await asyncio.to_thread(zlepi, ai)
        except Exception as e:
            print(f"[meta-ads] podaljšanje 4:5: {e}")
            return platno

    def podaljsaj_23(raw):
        """4:5 slika → 1024×1536 (2:3): zgoraj/spodaj zamegljen podaljšek robnih vrstic, sredina = izvirnik (1024×1280)."""
        from PIL import Image, ImageFilter
        im = Image.open(io.BytesIO(raw)).convert("RGB").resize((1024, 1280))
        c = Image.new("RGB", (1024, 1536))
        c.paste(im.crop((0, 0, 1024, 40)).resize((1024, 128)).filter(ImageFilter.GaussianBlur(12)), (0, 0))
        c.paste(im.crop((0, 1240, 1024, 1280)).resize((1024, 128)).filter(ImageFilter.GaussianBlur(12)), (0, 1408))
        c.paste(im, (0, 128))
        b = io.BytesIO(); c.save(b, format="JPEG", quality=92); return b.getvalue()

    def prompt_kreativa(ime, vibe, tekst, hook="", razmerje="1:1", scena="", smer=""):
        """Prompt generatorja Kreative (/generate-kreative) + HOOK: velik hook napis zgoraj, ime izdelka kot MANJŠI logo
        (sam branding kupcu še nič ne pove — uporabnik 2026-10-15). Brez hooka = točno prompt generatorja."""
        if hook:
            napisi = (f"Do not include any text/words on the image except: (1) a short, big, bold HOOK headline '{hook}' — the most prominent text, "
                      f"high contrast; (2) the device name in capital letters '{ime.upper()}' as a SMALL logo (clearly smaller than the hook) — never the biggest element. ")
        else:
            napisi = f"Do not include any text/words on the image except the device name in capital letters '{ime.upper()}' — place it where it fits best or makes sense. "
        sc = MA_SCENE.get(scena) or {}
        if scena == "eksperiment":   # 🧪 drzna smer: samo izdelek, hook in prednosti so obvezni, slog in postavitev prosta
            sc = {"scena": f"EXPERIMENTAL CREATIVE — be bold and different from a typical e-commerce ad. Art direction: {smer} ",
                  "postavitev": "choose a bold, unexpected layout that fits this art direction, but keep the hook big and readable and the 3 benefits clear."}
            vibe = vibe or "bold experimental"
        return ("From these reference images create a new FB ad creative. "
                + (f"SCENE TYPE — {sc['scena']} The product must look EXACTLY like in the reference images (same shape, colours, parts). " if sc else "")
                + f"Try a more intense '{vibe}' background. "
                + napisi
                + (f"LAYOUT: {sc['postavitev']} " if sc else "") +
                f"If possible (if you recognize any suitable English naming styles), you can also create a logo from the name. "
                f"Highlight (can be through icons or text in English) that it is: {tekst}. "
                f"Keep all text and icons well within the image borders — nothing should be cut off at the edges. "
                + "Square 1:1 format.")   # 4:5 = 1:1 + podaljšano ozadje (kvadrat_v_45)

    # 📐 4:5 (2026-10-16 b): Flare je hook risal do roba in naš obrez 2:3 → 4:5 ga je odrezal (2× kljub navodilom v promptu) →
    # kreativa se nariše kot 1:1 in se podaljša samo ozadje (kvadrat_v_45) → vse pomembno v osrednjem kvadratu (tudi za FB obrez na 1:1)

    def prompt_prevod(t, ime):
        """Isti prompt kot »Lok« (prevod slik): prevedi vidno besedilo, vse ostalo enako; ime izdelka/logo ostane."""
        lang = t.upper()
        lang_name = (G.get("LANG_NAMES") or {}).get(lang, MA_JEZIK[t])
        hint = (G.get("LANG_TRANSLATE_HINTS") or {}).get(lang, "")
        brand_note = f" Do NOT translate these brand/product names (keep exactly as-is): {ime}." if ime else ""
        return (f"Edit this image to translate all visible text into {lang_name}. "
                f"Keep EVERYTHING exactly the same — same people, same background, same layout, same design, same product, same icons, same colors, same fonts. "
                f"ONLY translate the text that is NOT a brand name or logo."
                f"{brand_note} "
                f"Do NOT translate or modify any brand names, logos, or product names. "
                f"Keep all text in the same position, same style, same size. "
                f"CRITICAL TRANSLATION QUALITY: Use ONLY correct, native {lang_name}. "
                f"Do NOT use words from other similar/neighboring languages. "
                f"Translate the MEANING correctly, not phonetically. "
                f"{hint}")

    async def prenesi(urls, n=3):
        import httpx
        out = []
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as hc:
            for u in urls:
                if len(out) >= n:
                    break
                try:
                    r = await hc.get(u)
                    if r.status_code == 200 and r.content:
                        m = (r.headers.get("content-type") or "image/jpeg").split(";")[0]
                        if m not in ("image/jpeg", "image/png", "image/webp"):
                            from PIL import Image
                            b = io.BytesIO(); Image.open(io.BytesIO(r.content)).convert("RGB").save(b, "JPEG", quality=92)
                            out.append((b.getvalue(), "image/jpeg"))
                        else:
                            out.append((r.content, m))
                except Exception as e:
                    print(f"[meta-ads] ref {u[:60]}: {e}")
        return out

    # ── Asana videi ──
    async def asana_videi(pid, sku, povezave):
        import httpx, os
        token = os.environ.get("ASANA_API_KEY", "")
        if not token:
            return [], ["ASANA_API_KEY ni nastavljen"]
        api = G.get("ASANA_API") or "https://app.asana.com/api/1.0"
        mapa = MAPA / pid / "videi"
        mapa.mkdir(parents=True, exist_ok=True)
        videi, nap = [], []
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as hc:
            for pov in povezave:
                m = re.search(r"/task/(\d+)", pov) or re.search(r"(\d{10,})\D*$", pov)
                if not m:
                    nap.append(f"ni ID taska: {pov[:60]}"); continue
                r = await hc.get(f"{api}/tasks/{m.group(1)}/attachments", params={"opt_fields": "name,size,download_url"},
                                 headers={"Authorization": f"Bearer {token}"})
                if r.status_code != 200:
                    nap.append(f"Asana {m.group(1)}: HTTP {r.status_code}"); continue
                for a in (r.json().get("data") or []):
                    ime = a.get("name") or ""
                    if not re.search(r"\.(mp4|mov|m4v)$", ime, re.I) or not a.get("download_url"):
                        continue
                    n = len(videi) + 1
                    fn = f"{sku}_video{n}.mp4"
                    try:
                        v = await hc.get(a["download_url"])
                        if v.status_code != 200:
                            raise RuntimeError(f"HTTP {v.status_code}")
                        (mapa / fn).write_bytes(v.content)
                        mb = len(v.content) / 1048576
                        videi.append({"datoteka": fn, "izvor": ime, "mb": round(mb, 1), "vkljuci": mb <= 10 and n <= 5,
                                      "opomba": "nad 10 MB — Meta uvoz ga ne sprejme" if mb > 10 else ""})
                    except Exception as e:
                        nap.append(f"video {ime[:40]}: {str(e)[:80]}")
        return videi, nap

    # ── 1) koncept: A/B opcije kot generator Kreative (/analyze-product-kreative) + SLO besedila oglasov ──
    MA_PARI = [(0, 0), (1, 1), (0, 2), (1, 3), (2, 4)]   # (A, B): MAIN×BEST, HIGH×SECOND, MAIN×SCROLL STOPPER, HIGH×BONUS, PROBLEM×LIFESTYLE

    async def kreative_ab(url, naziv, opis):
        """→ (ime, a_opcije, b_opcije). Najprej isti endpoint kot generator Kreative; rezerva: enak format iz opisa."""
        j = {}
        if url and G.get("analyze_product_kreative"):
            try:
                j = await G["analyze_product_kreative"]({"url": url}) or {}
            except Exception as e:
                print(f"[meta-ads] analiza Kreative: {e}")
        if not (j.get("aOptions") and j.get("bOptions")):
            j = await asyncio.to_thread(claude_json, (
                "Generate structured data for FB ad creatives for this product. ALL in ENGLISH.\n"
                f"Product: {naziv}\nDescription: {opis[:1800]}\n"
                "name: brand/model name in CAPS. aOptions: exactly 5 (labels MAIN VERSION, HIGH-CONVERT, PROBLEM-SOLUTION, ULTRA SIMPLE, SOCIAL PROOF), "
                "text = selling punches (not features), 2–3 words each, comma separated (e.g. 'Pull the Root, Stop the Weed, No Chemicals'). "
                "bOptions: exactly 5 (labels BEST, SECOND OPTION, SCROLL STOPPER, BONUS, LIFESTYLE), text = background vibe concept specific to this product, "
                "max 3 words, always an action or moment (e.g. 'evening atmosphere shot', 'before/after counter').\n"
                'Return ONLY JSON: {"name": "...", "aOptions": [{"label": "...", "text": "..."}], "bOptions": [{"label": "...", "text": "..."}]}'), 3000)
        a = [x for x in (j.get("aOptions") or []) if x.get("text")]
        b = [x for x in (j.get("bOptions") or []) if x.get("text")]
        return re.sub(r"[^A-Z0-9 \-&]", "", str(j.get("name") or "").upper())[:20].strip(), a, b

    def hooki_ai(naziv, opis, kreative):
        """En angleški HOOK na kreativo (velik napis zgoraj na sliki): problem / korist / radovednost, max 5 besed, ujema se s prednostmi A."""
        j = claude_json(
            "Write one scroll-stopping HOOK headline in ENGLISH for each Facebook ad image below (big text at the top of the image). "
            "Max 5 words, punchy, a problem, benefit or curiosity — not the product name, no prices, no '#1/best', no medical claims. "
            "Each hook must match that image's benefits and be different from the others (e.g. 'Cold Feet? Not Anymore', 'Winter Walks, Warm Toes').\n"
            f"Product: {naziv}\nDescription: {opis[:1200]}\n"
            + "\n".join(f"{i + 1}. benefits: {k['tekst']} · scene: {k['vibe']}" for i, k in enumerate(kreative))
            + '\nReturn ONLY JSON: {"hooki": ["...", ...same count]}', 2000)
        h = [str(x).strip()[:40] for x in (j.get("hooki") or [])]
        return h if len(h) == len(kreative) else [""] * len(kreative)

    def razvrsti_galerijo(urls):
        """Sonnet vision: vloga vsake slike galerije (packshot / uporaba / detajl / okolje / prej_potem / izlocena = besedilo, infografika, kolaž)."""
        vsebina = [{"type": "text", "text": (
            "These are e-commerce product gallery images. Classify EACH image into exactly one role: "
            "packshot = product alone, clean/simple background, no text; uporaba = product being used by a person / in hands; "
            "detajl = close-up of a detail, texture or the set/package contents; okolje = product in its real environment / lifestyle scene; "
            "prej_potem = before/after comparison; izlocena = contains text, letters, numbers, arrows, badges, infographic, collage, or other products. "
            "Also pick the single best packshot (most faithful, whole product visible). "
            'Return ONLY JSON: {"vloge": {"0": "packshot", "1": "uporaba", ...}, "najboljsi_packshot": 0}')}]
        for i, u in enumerate(urls):
            vsebina += [{"type": "text", "text": f"Image {i}:"}, {"type": "image", "source": {"type": "url", "url": u}}]
        msg = G["client"].messages.create(model="claude-sonnet-4-6", max_tokens=3000, messages=[{"role": "user", "content": vsebina}])
        j = beri_json("".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"))
        vloge = {int(k): str(v) for k, v in (j.get("vloge") or {}).items() if str(k).isdigit() and int(k) < len(urls)}
        try:
            naj = int(j.get("najboljsi_packshot"))
        except (TypeError, ValueError):
            naj = next((i for i, v in vloge.items() if v == "packshot"), 0)
        return vloge, (naj if 0 <= naj < len(urls) else 0)

    def reference_za(urls, vloge, naj, scena, i):
        """packshot (zvestoba izdelka) + do 2 sliki, ki ustrezata sceni; brez slik z besedilom. Različne kreative dobijo različne slike."""
        dobre = [k for k in range(len(urls)) if vloge.get(k) != "izlocena"] or list(range(len(urls)))
        vloga = MA_SCENE[scena]["vloga"]
        ujemajo = [k for k in dobre if vloge.get(k) == vloga and k != naj]
        ostale = [k for k in dobre if k != naj and k not in ujemajo]
        ostale = ostale[i % len(ostale):] + ostale[:i % len(ostale)] if ostale else []   # zamik → vsaka kreativa drugo dodatno sliko
        izb = [naj] + (ujemajo + ostale)[:2]
        return [urls[k] for k in dict.fromkeys(izb)]

    def oglasi_ai(naziv, opis, prednosti, n_oglasov):
        prompt = (
            f"Napiši {n_oglasov} RAZLIČNIH Facebook/Instagram oglasov v SLOVENŠČINI za izdelek trgovine Maaarket.\n"
            f"Izdelek: {naziv}\nOpis (lahko v drugem jeziku — uporabi pomen): {opis[:1800]}\nKljučne prednosti (angleško): {prednosti}\n"
            "Vsak oglas: pt (Primary Text): 2–3 vrstice, 2–3 emoji-ji, prodajni ton, brez cen, vsak DRUGAČEN (problem, korist, uporaba, mnenja, radovednost); "
            "hl (Headline): MAX 5 BESED, 1 emoji na začetku, brez cen, vsak DRUGAČEN.\n"
            f"EMOJI PRAVILO: uporabljaj SAMO te emoji-je (drugi se lahko prikažejo kot □): {MA_EMOJI}\n"
            "Pravila Mete: brez cen in popustov, brez 'najboljši/#1', brez zdravstvenih obljub, brez osebnih lastnosti ('Imaš prekomerno težo?'); šumniki č š ž.\n"
            'Vrni SAMO JSON: {"oglasi": [{"hl": "...", "pt": "..."}]}')
        j = claude_json(prompt)
        return [{"hl": str(o.get("hl") or "").strip(), "pt": str(o.get("pt") or "").strip()} for o in (j.get("oglasi") or []) if o][:n_oglasov]

    async def obdelaj_koncept(pid):
        p = pak_get(pid)
        try:
            sku = p["sku"]
            info = await izdelek_po_trgih(sku)
            sl = info.get("sl") or next(iter(info.values()), None)
            if not sl:
                await pak_set(pid, lambda q: q.update(status="napaka", napaka=f"SKU {sku} ni v nobenem feedu (Marža po trgih)."))
                return
            feed_sl = G["feed_by_lang"].get("sl") or {}
            it = feed_sl.get(sl.get("g_id")) or {}
            slike = it.get("all_images") or ([sl.get("slika")] if sl.get("slika") else [])
            if G.get("_kbatch_images_by_sku"):   # 🖼 cela galerija po SKU (isti vir kot Optimizacija slik: glavna + galerija)
                try:
                    gal = await G["_kbatch_images_by_sku"](sku, 14)
                    slike = list(dict.fromkeys([u for u in (gal or []) + slike if u]))[:14]
                except Exception as e:
                    print(f"[meta-ads] galerija {sku}: {e}")
            videi, nap = await asana_videi(pid, sku, p.get("asana") or []) if p.get("asana") else ([], [])
            n_ogl = MA_N_KREATIV + len(videi)
            naziv = sl.get("naziv") or it.get("title") or sku
            ime, a_opc, b_opc = await kreative_ab(sl.get("url") or "", naziv, it.get("description") or "")
            if not (a_opc and b_opc):
                raise RuntimeError("analiza izdelka ni vrnila A/B opcij")
            kre = []
            for ia, ib in MA_PARI[:MA_N_KREATIV]:
                a_, b_ = a_opc[ia % len(a_opc)], b_opc[ib % len(b_opc)]
                kre.append({"oznaka": f"{a_.get('label', 'A')} × {b_.get('label', 'B')}", "tekst": str(a_["text"]).strip()[:120], "vibe": str(b_["text"]).strip()[:60],
                            "razmerje": "1:1"})   # 4 × 1:1 + 1 × 4:5 (preizkus mobilni Feed)
            hk, ogl = await asyncio.gather(asyncio.to_thread(hooki_ai, naziv, it.get("description") or "", kre),
                                           asyncio.to_thread(oglasi_ai, naziv, it.get("description") or "", a_opc[0]["text"], max(n_ogl, MA_N_KREATIV)))
            for k_, h_ in zip(kre, hk):
                k_["hook"] = h_
            try:
                vloge, naj = await asyncio.to_thread(razvrsti_galerijo, slike[:12]) if len(slike) > 1 else ({}, 0)
            except Exception as e:
                print(f"[meta-ads] razvrstitev galerije: {e}")
                vloge, naj = {}, 0
            for i_, k_ in enumerate(kre):
                k_["scena"] = MA_SCENE_RED[i_ % len(MA_SCENE_RED)]
                k_["refs"] = reference_za(slike[:12], vloge, naj, k_["scena"], i_) if slike else []
            trgi = {}
            for t in MA_TRGI:
                x = info.get(t)
                trgi[t] = {"url": (x or {}).get("url", ""), "g_id": (x or {}).get("g_id", ""), "naziv": (x or {}).get("naziv", ""),
                           "neuvoz": bool((x or {}).get("neuvoz")),
                           "vkljuci": bool(x and x.get("url")) and t in (p.get("trgi_izbor") or MA_TRGI) and not (x or {}).get("neuvoz"),
                           "stran": MA_STRAN_TRG[t]}
                if not x:
                    trgi[t]["opomba"] = "ni v feedu trga"
                elif x.get("neuvoz"):
                    trgi[t]["opomba"] = "🚫 ne uvažamo (Marža)"
            auto = bool(p.get("auto_osnove")) and bool(slike)   # 🧵 vrsta: kreative se narišejo takoj po konceptu
            for k_ in kre if auto else []:
                k_["v_delu"] = True
            await pak_set(pid, lambda q: q.update(status="osnove_v_delu" if auto else "koncept", ime=ime or sku, naziv=sl.get("naziv") or "", kreative=kre, oglasi_sl=ogl,
                                                    videi=videi, opozorila=nap, ref_slike=slike[:12], galerija_vloge={str(k): v for k, v in vloge.items()}, trgi=trgi))
            if auto:
                asyncio.create_task(obdelaj_osnove(pid, list(range(len(kre)))))
        except Exception as e:
            print(f"[meta-ads] koncept {pid}: {e}")
            err = str(e)[:200]
            await pak_set(pid, lambda q: q.update(status="napaka", napaka=f"Koncept ni uspel: {err}"))

    # ── 2) kreative v angleščini (isti prompt + Flare kot generator Kreative) ──
    async def obdelaj_osnove(pid, indeksi):
        p = pak_get(pid)
        mapa = MAPA / pid
        mapa.mkdir(parents=True, exist_ok=True)
        if not (p.get("ref_slike") or any(k.get("refs") for k in p["kreative"])):
            await pak_set(pid, lambda q: q.update(status="koncept", napaka="Ni referenčnih slik izdelka (feed)."))
            return

        async def ena(i):
            k = p["kreative"][i]
            try:
                razm = "1:1"   # 2026-10-16: vse kreative 1:1 (Meta pri Add media sama naredi 4:5 / 9:16 / 1,91:1)
                # 4:5: Flare varne cone ne drži (hook do roba → obrez ga odreže) → nariši 1:1 (postavitev drži) + podaljšaj samo ozadje do 4:5
                refs = await prenesi(k.get("refs") or p.get("ref_slike") or [], 3)
                if not refs:
                    raise RuntimeError("referenčnih slik ni bilo mogoče prenesti")
                smer = random.choice(MA_EKSPERIMENTI) if k.get("scena") == "eksperiment" else ""
                raw = await flare(refs, prompt_kreativa(p.get("ime") or p["sku"], k.get("vibe") or "lifestyle", k.get("tekst") or "", k.get("hook") or "", "1:1",
                                                        k.get("scena") or "", smer), "1:1", n_ref=3)
                if razm == "4:5":
                    raw = await kvadrat_v_45(raw)
                fn = f"osnova_{i + 1}_{uuid.uuid4().hex[:4]}.jpg"
                (mapa / fn).write_bytes(raw)
                await pak_set(pid, lambda q: q["kreative"][i].update(osnova=fn, osnova_napaka="", v_delu=False, razmerje=razm, smer=smer.split(":")[0].title() if smer else ""))
            except Exception as e:
                err = str(e)[:160]
                await pak_set(pid, lambda q: q["kreative"][i].update(osnova_napaka=err, v_delu=False))
        await asyncio.gather(*(ena(i) for i in indeksi))
        await pak_set(pid, lambda q: q.update(status="osnove"))

    # ── 3) lokalizacija: prevodi + besedilo na slikah po trgih ──
    def prevedi(t, ogl):
        jez = MA_JEZIK[t]
        prompt = (
            f"Translate these Facebook ad texts from Slovenian into {jez}. Native, natural marketing language (not literal), correct grammar and "
            "diacritics; keep the number and position of emojis exactly; keep brand/product names unchanged; headlines max 5 words.\n"
            f"ads: {json.dumps(ogl, ensure_ascii=False)}\n"
            'Return ONLY JSON: {"ads": [{"hl": "...", "pt": "..."}, ...same count]}')
        j = claude_json(prompt)
        ads = [{"hl": str(a.get("hl") or "").strip(), "pt": str(a.get("pt") or "").strip()} for a in (j.get("ads") or [])]
        if len(ads) != len(ogl):
            raise RuntimeError("prevod: napačno število oglasov")
        return ads

    async def tekst_slika(pid, t, i, model):
        """Angleška kreativa → napisi v jeziku trga (prompt »Lok«), NB2.1 ali Flare."""
        p = pak_get(pid)
        k = p["kreative"][i]
        osn = MAPA / pid / (k.get("osnova") or "")
        if not k.get("osnova") or not osn.exists():
            raise RuntimeError("ni angleške kreative")
        pr = prompt_prevod(t, p.get("ime") or "")
        from PIL import Image as _Im
        with _Im.open(osn) as _im:   # razmerje iz dejanske slike (stari paketi imajo lahko 4:5)
            razm = "4:5" if _im.height > _im.width * 1.1 else "1:1"
        if model == "flare" and razm == "4:5":   # Flare vrne 2:3 → brez podaljšanja bi drugi obrez odrezal hook/ikone
            raw = await flare([(await asyncio.to_thread(podaljsaj_23, osn.read_bytes()), "image/jpeg")],
                              pr + " The top and bottom bands are only a background extension — keep them as plain background, do not add anything there.", razm)
        else:
            raw = await (flare([(osn.read_bytes(), "image/jpeg")], pr, razm) if model == "flare" else nb21(osn.read_bytes(), pr, razm))
        fn = f"{p['sku']}_{t}_{i + 1}.jpg"
        (MAPA / pid / fn).write_bytes(raw)
        return fn

    async def obdelaj_lokal(pid, model, samo=None):
        """samo = [(trg, i)] → samo te slike znova (brez prevodov)."""
        p = pak_get(pid)
        trgi = [t for t in MA_TRGI if p["trgi"][t].get("vkljuci")]
        if not samo:
            ogl_sl = p["oglasi_sl"]

            async def prevod(t):
                if t == "sl":
                    await pak_set(pid, lambda q: q["trgi"]["sl"].update(oglasi=[dict(o) for o in q["oglasi_sl"]], prevod_napaka=""))
                    return
                try:
                    ads = await asyncio.to_thread(prevedi, t, ogl_sl)
                    await pak_set(pid, lambda q: q["trgi"][t].update(oglasi=ads, prevod_napaka=""))
                except Exception as e:
                    err = str(e)[:160]
                    await pak_set(pid, lambda q: q["trgi"][t].update(prevod_napaka=err))
            await asyncio.gather(*(prevod(t) for t in trgi))
            p = pak_get(pid)
            samo = [(t, i) for t in trgi if not p["trgi"][t].get("prevod_napaka") for i in range(len(p["kreative"])) if p["kreative"][i].get("osnova")]

        async def ena(t, i):
            try:
                fn = await tekst_slika(pid, t, i, model)
                await pak_set(pid, lambda q: q["trgi"][t].setdefault("slike", {}).update({str(i): {"datoteka": fn, "model": model}}))
            except Exception as e:
                err = str(e)[:160]
                await pak_set(pid, lambda q: q["trgi"][t].setdefault("slike", {}).update({str(i): {"napaka": err}}))
            finally:
                await pak_set(pid, lambda q: q.update(lok_gotovo=int(q.get("lok_gotovo") or 0) + 1))
        await pak_set(pid, lambda q: q.update(lok_skupaj=len(samo), lok_gotovo=0))
        await asyncio.gather(*(ena(t, i) for t, i in samo))
        await pak_set(pid, lambda q: q.update(status="pripravljeno", model_tekst=model))

    # ── API ──
    @app.get("/meta-ads")
    async def ma_stran(request: Request):
        return FileResponse("static/meta_ads.html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    def statistika(d):
        danes = _lj_iso()[:10]
        ev = d.get("evidenca") or []
        dnevi = {}
        for e in ev:
            dnevi[e["at"][:10]] = dnevi.get(e["at"][:10], 0) + int(e.get("oglasov") or 0)
        od = datetime.strptime(danes, "%Y-%m-%d") - timedelta(days=13)
        return {"danes": {"oglasi": sum(int(e.get("oglasov") or 0) for e in ev if e["at"][:10] == danes),
                          "kampanje": len({e["sku"] for e in ev if e["at"][:10] == danes})},
                "skupaj": {"oglasi": sum(int(e.get("oglasov") or 0) for e in ev), "kampanje": len({e["sku"] for e in ev}),
                           "slike": sum(int(e.get("slik") or 0) for e in ev)},
                "dnevi": [{"d": (od + timedelta(days=i)).strftime("%Y-%m-%d"), "n": dnevi.get((od + timedelta(days=i)).strftime("%Y-%m-%d"), 0)} for i in range(14)]}

    @app.get("/meta-ads/api/stanje")
    async def ma_stanje(request: Request):
        if not prijava(request):
            return ni()
        d = nalozi()
        return {"ok": True, "stat": statistika(d), "brez_rs": d["brez_rs"], "vrsta": d.get("vrsta") or {"postavke": []}, "strani": MA_STRANI, "jeziki": MA_JEZIK_SL, "cta": MA_CTA, "bid": MA_BID, "scene": {k: v["ime"] for k, v in MA_SCENE.items()},
                "paketi": [{k: p.get(k) for k in ("id", "sku", "ime", "status", "at", "izvozeno")} |
                           {"trgi": [t for t in MA_TRGI if ((p.get("trgi") or {}).get(t) or {}).get("vkljuci")]} for p in d["paketi"]]}

    @app.get("/meta-ads/api/sku")
    async def ma_sku(request: Request, sku: str = ""):
        """Kateri trgi imajo SKU v feedu (URL) + 🚫 neuvoz + zapomnjen »brez RS«."""
        if not prijava(request):
            return ni()
        sku = sku.strip().upper()
        if not sku:
            return {"ok": False, "error": "Vpiši SKU."}
        info = await izdelek_po_trgih(sku)
        d = nalozi()
        nar = [e for e in d["evidenca"] if e["sku"] == sku]
        return {"ok": True, "sku": sku, "trgi": {t: {"url": bool((info.get(t) or {}).get("url")), "neuvoz": bool((info.get(t) or {}).get("neuvoz"))} for t in MA_TRGI},
                "naziv": (info.get("sl") or next(iter(info.values()), {}) or {}).get("naziv", ""), "brez_rs": sku in d["brez_rs"],
                "narejeno": nar[-1] if nar else None}

    @app.post("/meta-ads/api/koncept")
    async def ma_koncept(request: Request, data: dict):
        if not prijava(request):
            return ni()
        sku = str(data.get("sku") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_\-\.]{2,40}$", sku):
            return {"ok": False, "error": "Vpiši en veljaven SKU."}
        async with lock:
            d = nalozi()
            pid = nov_paket(d, sku, data.get("trgi"), data.get("asana"))
            _jsave(PAK_FILE, d)
        asyncio.create_task(obdelaj_koncept(pid))
        return {"ok": True, "id": pid}

    def nov_paket(d, sku, trgi, asana, auto_osnove=False):
        """Nov paket v d (klicatelj drži lock in shrani) → pid; koncept zažene klicatelj."""
        trgi_izbor = [t for t in (trgi or MA_TRGI) if t in MA_TRGI] or MA_TRGI
        asana = [s.strip() for s in re.split(r"[\s,]+", str(asana or "")) if "asana.com" in s or re.fullmatch(r"\d{10,}", s.strip())][:5]
        pid = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
        if "rs" in trgi_izbor:   # 🚫 zapomni »brez RS« po SKU (carina)
            d["brez_rs"] = [s for s in d["brez_rs"] if s != sku]
        elif sku not in d["brez_rs"]:
            d["brez_rs"].append(sku)
        d["paketi"].insert(0, {"id": pid, "sku": sku, "at": _lj_iso(), "status": "koncept_v_delu", "trgi_izbor": trgi_izbor, "asana": asana,
                               "auto_osnove": auto_osnove,
                               "nastavitve": {"proracun": 60, "status": "ACTIVE", "kampanja": f"{MA_ZNAK} [ALL 9.0BID] {sku} #BidCap (Suban)"}})
        for p in d["paketi"][30:]:   # stari paketi: slike/videi z diska
            import shutil
            shutil.rmtree(MAPA / p["id"], ignore_errors=True)
        d["paketi"] = d["paketi"][:30]
        return pid

    # ── 🧵 VRSTA (2026-10-20): več SKU-jev EDEN PO EDEN — koncept + kreative za trenutnega, ti pregledaš, lokaliziraš,
    #    📁 shraniš v mapo → šele nato se začne naslednji (d["vrsta"] = {postavke: [{sku, asana, trgi, status, pid}], auto})
    def vrsta_zacni_naslednjega(d):
        """V lock-u: prvi »caka« → nov paket; vrne pid ali None (vrsta končana / že kdo v delu)."""
        vr = d.get("vrsta") or {}
        ps = vr.get("postavke") or []
        if any(x.get("status") == "v_delu" for x in ps):
            return None
        x = next((x for x in ps if x.get("status") == "caka"), None)
        if not x:
            return None
        x["pid"] = nov_paket(d, x["sku"], x.get("trgi"), x.get("asana"), auto_osnove=vr.get("auto", True))
        x["status"] = "v_delu"; x["zacetek"] = _lj_iso()
        return x["pid"]

    @app.post("/meta-ads/api/vrsta")
    async def ma_vrsta(request: Request, data: dict):
        """{postavke: [{sku, asana, trgi}], auto} = nova vrsta (zamenja staro), {akcija: naslednji|preskoci, id} = trenutni končan → naslednji, {akcija: pocisti}."""
        if not prijava(request):
            return ni()
        akcija = data.get("akcija") or "nova"
        async with lock:
            d = nalozi()
            vr = d.setdefault("vrsta", {"postavke": []})
            if akcija == "nova":
                ps = []
                for x in data.get("postavke") or []:
                    sku = str(x.get("sku") or "").strip().upper()
                    if re.match(r"^[A-Z0-9_\-\.]{2,40}$", sku) and sku not in [y["sku"] for y in ps]:
                        trgi = [t for t in (x.get("trgi") or MA_TRGI) if t in MA_TRGI]
                        if "rs" in trgi:   # 🚫 zapomni »brez RS« po SKU (kot pri konceptu)
                            d["brez_rs"] = [s for s in d["brez_rs"] if s != sku]
                        elif sku not in d["brez_rs"]:
                            d["brez_rs"].append(sku)
                        ps.append({"sku": sku, "asana": str(x.get("asana") or ""), "trgi": trgi, "status": "caka"})
                if not ps:
                    return {"ok": False, "error": "Ni veljavnih SKU-jev."}
                d["vrsta"] = vr = {"postavke": ps[:60], "auto": data.get("auto", True) is not False, "at": _lj_iso()}
            elif akcija in ("naslednji", "preskoci"):
                pid = str(data.get("id") or "")
                for x in vr.get("postavke") or []:
                    if x.get("status") == "v_delu" and (not pid or x.get("pid") == pid):
                        x["status"] = "shranjeno" if akcija == "naslednji" else "preskoceno"; x["konec"] = _lj_iso()
            elif akcija == "pocisti":
                d["vrsta"] = vr = {"postavke": []}
            nov = vrsta_zacni_naslednjega(d) if akcija != "pocisti" else None
            _jsave(PAK_FILE, d)
        if nov:
            asyncio.create_task(obdelaj_koncept(nov))
        return {"ok": True, "id": nov, "vrsta": vr}

    @app.post("/meta-ads/api/izbrisi")
    async def ma_izbrisi(request: Request, data: dict):
        """🗑 Izbriše paket(e) iz zgodovine + njihove slike/videe z diska. Števec (evidenca) ostane. {id} ali {vse: true}."""
        if not prijava(request):
            return ni()
        import shutil
        async with lock:
            d = nalozi()
            if data.get("vse"):
                ids = [p["id"] for p in d["paketi"] if p.get("status") not in ("koncept_v_delu", "osnove_v_delu", "lokal_v_delu")]
            else:
                ids = [str(data.get("id") or "")]
            ids = [i for i in ids if re.fullmatch(r"[0-9a-f]{18}", i)]
            d["paketi"] = [p for p in d["paketi"] if p["id"] not in ids]
            _jsave(PAK_FILE, d)
        for i in ids:
            shutil.rmtree(MAPA / i, ignore_errors=True)
        return {"ok": True, "izbrisanih": len(ids)}

    @app.get("/meta-ads/api/paket/{pid}")
    async def ma_paket(request: Request, pid: str):
        if not prijava(request):
            return ni()
        p = pak_get(pid)
        return {"ok": True, "paket": p} if p else {"ok": False, "error": "Paketa ni."}

    @app.post("/meta-ads/api/shrani")
    async def ma_shrani(request: Request, data: dict):
        """Popravki: ime, kreative (vibe, bullets SL), oglasi_sl, videi (vkljuci), trgi (vkljuci, stran, oglasi, bullets), nastavitve, izkl."""
        if not prijava(request):
            return ni()
        pid = str(data.get("id") or "")

        def upd(p):
            if data.get("ime"):
                p["ime"] = re.sub(r"[^A-Z0-9 \-&]", "", str(data["ime"]).upper())[:20].strip() or p.get("ime")
            for i, k in enumerate(data.get("kreative") or []):
                if i < len(p.get("kreative") or []):
                    p["kreative"][i]["vibe"] = str(k.get("vibe") or p["kreative"][i].get("vibe") or "")[:60]
                    p["kreative"][i]["tekst"] = str(k.get("tekst") or p["kreative"][i].get("tekst") or "")[:120]
                    if k.get("scena") in MA_SCENE:
                        p["kreative"][i]["scena"] = k["scena"]
                    if k.get("razmerje") in MA_SLIKA:
                        p["kreative"][i]["razmerje"] = k["razmerje"]
                    if "hook" in k:
                        p["kreative"][i]["hook"] = str(k.get("hook") or "").strip()[:40]
            if isinstance(data.get("oglasi_sl"), list):
                p["oglasi_sl"] = [{"hl": str(o.get("hl") or ""), "pt": str(o.get("pt") or "")} for o in data["oglasi_sl"]]
            for v in data.get("videi") or []:
                for x in p.get("videi") or []:
                    if x["datoteka"] == v.get("datoteka"):
                        x["vkljuci"] = bool(v.get("vkljuci"))
            for t, tv in (data.get("trgi") or {}).items():
                if t in (p.get("trgi") or {}):
                    for k_ in ("vkljuci", "stran"):
                        if k_ in tv:
                            p["trgi"][t][k_] = tv[k_]
                    if "bid" in tv:
                        try:
                            b_ = round(float(str(tv["bid"]).replace(",", ".")), 2)
                            if b_ > 0:
                                p["trgi"][t]["bid"] = b_
                        except ValueError:
                            pass
                    if isinstance(tv.get("oglasi"), list):
                        p["trgi"][t]["oglasi"] = [{"hl": str(o.get("hl") or ""), "pt": str(o.get("pt") or "")} for o in tv["oglasi"]]
                    if isinstance(tv.get("izkl"), list):
                        p["trgi"][t]["izkl"] = [str(x) for x in tv["izkl"]]
            if isinstance(data.get("nastavitve"), dict):
                n = p.setdefault("nastavitve", {})
                for k_ in ("proracun", "bid", "status", "kampanja"):
                    if k_ in data["nastavitve"]:
                        n[k_] = data["nastavitve"][k_]
        await pak_set(pid, upd)
        return {"ok": True}

    @app.post("/meta-ads/api/osnove")
    async def ma_osnove(request: Request, data: dict):
        if not prijava(request):
            return ni()
        pid = str(data.get("id") or "")
        p = pak_get(pid)
        if not p or not p.get("kreative"):
            return {"ok": False, "error": "Najprej pripravi koncept."}
        idx = [int(i) for i in (data.get("indeksi") or range(len(p["kreative"]))) if 0 <= int(i) < len(p["kreative"])]
        await pak_set(pid, lambda q: ([q["kreative"][i].update(v_delu=True, osnova_napaka="") for i in idx], q.update(status="osnove_v_delu")))
        asyncio.create_task(obdelaj_osnove(pid, idx))
        return {"ok": True}

    @app.post("/meta-ads/api/lokaliziraj")
    async def ma_lokaliziraj(request: Request, data: dict):
        if not prijava(request):
            return ni()
        pid = str(data.get("id") or "")
        p = pak_get(pid)
        if not p or not any(k.get("osnova") for k in p.get("kreative") or []):
            return {"ok": False, "error": "Najprej ustvari osnovne slike."}
        model = "flare" if data.get("model") == "flare" else "nb21"   # privzeto NB2.1 = isto kot »Lok« (prevod slik)
        samo = [(str(x[0]), int(x[1])) for x in (data.get("samo") or []) if x and x[0] in MA_TRGI]
        await pak_set(pid, lambda q: q.update(status="lokal_v_delu"))
        asyncio.create_task(obdelaj_lokal(pid, model, samo or None))
        return {"ok": True}

    @app.get("/meta-ads/api/datoteka/{pid}/{fn}")
    async def ma_datoteka(request: Request, pid: str, fn: str):
        if not prijava(request):
            return ni()
        if not re.fullmatch(r"[0-9a-f]{18}", pid) or not re.fullmatch(r"[A-Za-z0-9_\-\.]+", fn):
            return JSONResponse({"ok": False}, status_code=404)
        f = MAPA / pid / fn
        if not f.exists():
            f = MAPA / pid / "videi" / fn
        if not f.exists():
            return JSONResponse({"ok": False}, status_code=404)
        return FileResponse(str(f), headers={"Cache-Control": "private, max-age=3600"})

    def sestavi(p, status, nacin="loceni"):
        """→ (vrstice CSV, slike [fn], videi [fn], opozorila, rocno {trg: [slike]}).
        nacin »flex«: 1 oglas na trg (prva kreativa + 1 headline + 1 primary text) — ostale slike in videe dodaš ročno
        (Format → Flexible → Add media, v iskalniku »_pl«) — VSE slike v ENI mapi slike/ (uporabnik 2026-10-16); Flexible = 1 oglas → limit 250 / stran ni problem."""
        n = p.get("nastavitve") or {}
        kamp = str(n.get("kampanja") or f"[ALL 9.0BID] {p['sku']} #BidCap (Suban)").strip()
        if not kamp.startswith(MA_ZNAK):   # 🤖 = kampanja iz suban.ai (vedno spredaj, tudi če ime ročno spremeniš)
            kamp = f"{MA_ZNAK} {kamp}"
        st = "ACTIVE" if status == "ACTIVE" else "PAUSED"
        vrst, slike, videi, opz, rocno = [], set(), set(), [], {}
        nk = len(p.get("kreative") or [])
        vid = [(j, v) for j, v in enumerate(p.get("videi") or []) if v.get("vkljuci")]   # besedilo videa = po mestu v celem seznamu (5 + j)
        for t in MA_TRGI:
            tt = (p.get("trgi") or {}).get(t) or {}
            if not tt.get("vkljuci"):
                continue
            if not tt.get("url"):
                opz.append(f"{t.upper()}: ni URL-ja — izpuščen"); continue
            ogl = tt.get("oglasi") or []
            stran = MA_STRANI.get(tt.get("stran") or "") or MA_STRANI["101449685670882"]
            sid = tt.get("stran") if tt.get("stran") in MA_STRANI else "101449685670882"
            izkl = set(tt.get("izkl") or [])
            prva = None
            if nacin == "flex":   # vse slike trga v mapo za ročno dodajanje, v CSV samo prva
                rocno[t] = [s_ for s_ in (((tt.get("slike") or {}).get(str(i)) or {}).get("datoteka") for i in range(nk) if f"slika{i}" not in izkl) if s_]
                for j_, v in vid:
                    if f"video{j_}" not in izkl:
                        videi.add(v["datoteka"])
            enote = [("slika", i, i) for i in range(nk)] + [("video", j, nk + j) for j, _ in vid]
            vfile = {j: v["datoteka"] for j, v in vid}
            for vrsta, i, oi in enote:
                if f"{vrsta}{i}" in izkl:
                    continue
                o = ogl[oi] if oi < len(ogl) else {}
                if not (o.get("hl") and o.get("pt")):
                    opz.append(f"{t.upper()} oglas {oi + 1}: manjka besedilo — izpuščen"); continue
                if vrsta == "slika":
                    s = ((tt.get("slike") or {}).get(str(i)) or {}).get("datoteka")
                    if not s:
                        opz.append(f"{t.upper()} kreativa {i + 1}: ni slike — izpuščena"); continue
                    prva = prva or s
                    img, vfn, ct, an = s, "", "Link Page Post Ad", f"{p['sku']} {t.upper()} slika {i + 1} ({'eksperiment' if p['kreative'][i].get('scena') == 'eksperiment' else p['kreative'][i].get('razmerje') or '1:1'})"
                else:
                    if not prva:
                        opz.append(f"{t.upper()} video {i + 1}: ni sličice (nobene slike trga) — izpuščen"); continue
                    img, vfn, ct, an = prva, vfile[i], "Video Page Post Ad", f"{p['sku']} {t.upper()} video {i + 1}"
                r = dict(MA_STALNO)
                r.update({"Campaign Name": kamp, "Campaign Status": st, "Campaign Daily Budget": str(n.get("proracun") or 60),
                          "Ad Set Run Status": st, "Ad Set Name": MA_ADSET.get(t, t.upper()), "Countries": MA_DRZAVA[t], "Bid Amount": f"{float(tt.get('bid') or MA_BID.get(t, 9)):g}",
                          "Link Object ID": f"o:{sid}", "Optimized Conversion Tracking Pixels": f"tp:{MA_PIKSEL[t]}",
                          "Conversion Tracking Pixels": f"tp:{MA_PIKSEL[t]}", "Link": tt["url"],
                          "Ad Status": st, "Ad Name": an, "Title": o["hl"], "Body": o["pt"], "Image File Name": img,
                          "Video File Name": vfn, "Creative Type": ct,
                          "Instagram Account ID": f"x:{stran['ig_x']}" if stran.get("ig_x") else "",
                          "Instagram Account ID (New)": "" if stran.get("ig_x") else stran["ig"]})
                if nacin == "flex":
                    r["Ad Name"] = f"{p['sku']} {t.upper()} flexible"
                vrst.append(r)
                slike.add(img)
                if vfn:
                    videi.add(vfn)
                if nacin == "flex":
                    break   # 1 oglas na trg
        if len(videi) > 10 and nacin != "flex":
            opz.append(f"{len(videi)} videov — Meta sprejme največ 10 na uvoz")
        return vrst, sorted(slike), sorted(videi), opz, rocno

    async def zgradi_zip(pids, status, nacin):
        """1 ali več paketov (SKU-jev) → EN ZIP: en meta_uvoz.csv z vsemi kampanjami, ena mapa slike/, videi/ → en uvoz v Ads Manager."""
        nacin = "flex" if nacin == "flex" else "loceni"
        vse, opz_vse, deli = [], [], []
        for pid in pids:
            p = pak_get(pid)
            if not p:
                opz_vse.append(f"paket {pid} ne obstaja"); continue
            vrst, slike, videi, opz, rocno = sestavi(p, status, nacin)
            opz_vse += [f"{p['sku']}: {o}" for o in opz]
            if not vrst:
                opz_vse.append(f"{p['sku']}: ni nobenega oglasa — izpuščen"); continue
            vse += vrst
            deli.append((pid, p, vrst, slike, videi, rocno))
        if not vse:
            return None, opz_vse, 0
        buf = io.StringIO()
        w = csv.writer(buf, delimiter="\t", lineterminator="\r\n")
        w.writerow(GLAVE)
        for r in vse:
            w.writerow([r.get(k, "") for k in GLAVE])
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("meta_uvoz.csv", b"\xff\xfe" + buf.getvalue().encode("utf-16-le"))
            vec = len(deli) > 1   # več kampanj: mapa po SKU (SKU/slike, SKU/videi) → slike kampanj se ne pomešajo; CSV je skupen
            for pid, p, vrst, slike, videi, rocno in deli:
                pred = f"{p['sku']}/" if vec else ""
                for s_ in sorted(set(slike) | {x for sl_ in rocno.values() for x in sl_}):   # flex: vse kreative vseh trgov kampanje v isto mapo slike/
                    zf.write(MAPA / pid / s_, pred + "slike/" + s_)
                for v in videi:
                    zf.write(MAPA / pid / "videi" / v, pred + "videi/" + v, compress_type=zipfile.ZIP_STORED)
            koraki = ("1. Ads Manager → Import/Export → Import ads\r\n"
                      "2. File: meta_uvoz.csv\r\n3. Images: vse iz mape slike (Ctrl+A)\r\n4. Videos: vse iz mape videi (max 10 × 10 MB)\r\n"
                      "5. Import → preglej osnutke (In draft) → Publish\r\n") if nacin != "flex" else (
                      "1. Ads Manager → Import/Export → Import ads → File: meta_uvoz.csv, Images: VSE iz mape slike (Ctrl+A) → Import\r\n"
                      "2. Za vsak ad set (trg): odpri oglas »… flexible« → Format: Flexible → Add media → v iskalnik vpiši »SKU_pl« (oz. _sl, _ro …)\r\n"
                      "   → izberi slike trga + videe → headline in primary text ostaneta po 1 → Publish\r\n")
            zf.writestr("NAVODILA.txt", (
                f"Meta Ads uvoz — {', '.join(d_[1]['sku'] for d_ in deli)} — {_lj_iso()[:16]}\r\n\r\n"
                f"{len(deli)} kampanj, {len(vse)} oglasov, status: {status}, način: {'Flexible (ročno dopolni)' if nacin == 'flex' else 'ločeni oglasi'}.\r\n\r\n"
                + koraki
                + ("\r\nVeč kampanj: slike in videi so v mapi vsake kampanje (SKU\\slike, SKU\\videi). V zavihku Images naloži slike iz VSEH map SKU\r\n"
                   "(Choose images večkrat), nato v Add media iskalnik »SKU_pl« (npr. PANMAX_pl) → slike ene kampanje.\r\n" if vec else "")
                + "\r\n"
                + ("Opozorila:\r\n" + "\r\n".join(opz_vse) + "\r\n" if opz_vse else "")).encode("utf-8"))
        async with lock:
            d = nalozi()
            for pid, p, vrst, slike, videi, rocno in deli:
                px = next((x for x in d["paketi"] if x["id"] == pid), None)
                if px is None:
                    continue
                prvic = not px.get("izvozeno")
                px["izvozeno"] = _lj_iso()
                if prvic:   # 📊 števec: prvi izvoz paketa
                    d["evidenca"].append({"sku": p["sku"], "at": _lj_iso(), "oglasov": len(vrst), "slik": len(set(slike) | {x for sl_ in rocno.values() for x in sl_}),
                                          "nacin": nacin, "trgi": sorted({r["Ad Set Name"] for r in vrst})})
            _jsave(PAK_FILE, d)
        z.seek(0)
        return z, opz_vse, len(deli)

    @app.get("/meta-ads/api/izvoz/{pid}")
    async def ma_izvoz(request: Request, pid: str, status: str = "ACTIVE", nacin: str = "loceni"):
        """En paket ali več: pid = »id1,id2,…« (izbrani v zgodovini) → en CSV z vsemi kampanjami."""
        if not prijava(request):
            return ni()
        if not GLAVE:
            return JSONResponse({"ok": False, "error": "Manjka static/meta_ads_glave.json."}, status_code=500)
        pids = [x for x in pid.split(",") if re.fullmatch(r"[0-9a-f]{18}", x)][:30]
        if not pids:
            return JSONResponse({"ok": False, "error": "Paketa ni."}, status_code=404)
        z, opz, n = await zgradi_zip(pids, status, nacin)
        if not z:
            return JSONResponse({"ok": False, "error": "Ni nobenega oglasa za izvoz. " + " · ".join(opz[:5])}, status_code=400)
        ime = (pak_get(pids[0]) or {}).get("sku", "meta") if n == 1 else f"{n}_kampanj"
        return StreamingResponse(z, media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="meta_{ime}.zip"', "X-Opozorila": str(len(opz))})

    @app.post("/meta-ads/api/vec")
    async def ma_vec(request: Request, data: dict):
        """Množično za izbrane pakete: korak »osnove« (kreative) ali »lokaliziraj« — vsak paket v ozadju, kot ročni klik."""
        if not prijava(request):
            return ni()
        akcija = data.get("akcija")
        if akcija not in ("osnove", "lokaliziraj"):
            return {"ok": False, "error": "Neznana akcija."}
        model = "flare" if data.get("model") == "flare" else "nb21"
        ok, preskoceni = [], []
        for pid in [str(x) for x in (data.get("ids") or []) if re.fullmatch(r"[0-9a-f]{18}", str(x))][:30]:
            p = pak_get(pid)
            if not p or p.get("status") in ("koncept_v_delu", "osnove_v_delu", "lokal_v_delu") or not p.get("kreative"):
                preskoceni.append(pid); continue
            if akcija == "osnove":
                idx = list(range(len(p["kreative"])))
                await pak_set(pid, lambda q: ([q["kreative"][i].update(v_delu=True, osnova_napaka="") for i in idx], q.update(status="osnove_v_delu")))
                asyncio.create_task(obdelaj_osnove(pid, idx))
            else:
                if not any(k.get("osnova") for k in p["kreative"]):
                    preskoceni.append(pid); continue
                await pak_set(pid, lambda q: q.update(status="lokal_v_delu"))
                asyncio.create_task(obdelaj_lokal(pid, model, None))
            ok.append(pid)
        return {"ok": True, "zagnani": len(ok), "preskoceni": len(preskoceni)}
