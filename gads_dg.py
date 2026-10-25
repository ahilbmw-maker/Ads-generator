# 🎯 Google Ads → Demand Gen Bulk Creator (2026-10-14)
# Trg + obstoječa Demand Gen kampanja (iz izvoza Google Ads Editorja) + SKU-ji → AI besedila v jeziku trga (5 naslovov / 5 opisov),
# slike iz galerije feeda v 1:1, 1,91:1 in 4:5 → ZIP za Editor: ads.csv (UTF-16, TAB — preizkušeno: 2× Added, 0 Updated),
# images/<SKU>/…, manifest.csv, validation_report.csv. Slik Editor iz CSV NE pripne (preizkušeno) → uvozi jih »Import image assets
# from files« v knjižnico, pripneš ročno. Varovalke: brez stolpcev kampanje, brez ID-jev, brez Remove, vse Paused, dvojniki iz izvoza.
# Ločen modul (ne v main.py), vklop: gads_dg.vklopi(globals()) na koncu main.py.
import asyncio
import csv
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timedelta

DG_JEZIK = {"sl": "Slovenian", "hr": "Croatian", "rs": "Serbian (Latin script)", "hu": "Hungarian", "pl": "Polish",
            "cz": "Czech", "sk": "Slovak", "gr": "Greek", "bg": "Bulgarian", "ro": "Romanian"}
DG_TLD = {"si": "sl", "hr": "hr", "rs": "rs", "hu": "hu", "pl": "pl", "cz": "cz", "sk": "sk", "gr": "gr", "bg": "bg", "ro": "ro"}
DG_MAX = {"headline": 40, "description": 90, "business": 25}
DG_SLIKE = {"1x1": (1200, 1200), "191x1": (1200, 628), "4x5": (960, 1200)}
DG_STOLPCI = ["Campaign", "Ad Group", "Ad Group Type", "Channels", "Optimized targeting", "Ad Group Status", "Ad type", "Ad Name",
              "Headline 1", "Headline 2", "Headline 3", "Headline 4", "Headline 5",
              "Description 1", "Description 2", "Description 3", "Description 4", "Description 5",
              "Business name", "Video generation", "Adaptive layouts", "Final URL", "Status"]


# ── izvoz Editorja → kampanje, skupine, obstoječi SKU-ji, Business name, trg (po domeni Final URL) ──
def beri_izvoz(raw: bytes) -> list:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt = raw.decode("utf-16")
    else:
        txt = raw.decode("utf-8-sig", errors="replace")
    vrst = list(csv.reader(io.StringIO(txt), delimiter="\t"))
    if not vrst:
        return []
    h = [x.strip() for x in vrst[0]]
    ix = {k: i for i, k in enumerate(h)}
    g = lambda r, k: (r[ix[k]].strip() if k in ix and ix[k] < len(r) else "")
    kamp = {}
    for r in vrst[1:]:
        c = (r[ix["Campaign"]] if "Campaign" in ix and ix["Campaign"] < len(r) else "").strip("\r\n")   # ⚠ brez strip(): ime mora biti TOČNO kot v Editorju (presledki!), sicer uvoz ustvari novo (Search) kampanjo
        if not c.strip():
            continue
        k = kamp.setdefault(c, {"ime": c, "tip": "", "ad_groups": [], "skuji": [], "business_name": "", "trg": "", "primeri": [], "jeziki": "",
                                "kamp_vrstica": {}, "lokacije": []})
        if g(r, "Campaign Type"):
            k["tip"] = g(r, "Campaign Type"); k["jeziki"] = g(r, "Languages")
            k["kamp_vrstica"] = {h[i]: v for i, v in enumerate(r) if i < len(h) and v.strip()}   # vse nastavitve kampanje (kopija → nova)
        if g(r, "Location") and not g(r, "Ad Group"):
            k["lokacije"].append({h[i]: v for i, v in enumerate(r) if i < len(h) and v.strip() and h[i] not in ("Reach",)})
        ag = g(r, "Ad Group")
        if ag and g(r, "Ad Group Type") and ag not in k["ad_groups"]:
            k["ad_groups"].append(ag)
            m = re.search(r"SKU:\s*([A-Za-z0-9_\-\.]+)", ag)
            if m and m.group(1).upper() not in k["skuji"]:
                k["skuji"].append(m.group(1).upper())
        if g(r, "Ad type"):
            if g(r, "Business name"):
                k["business_name"] = g(r, "Business name")
            m = re.search(r"https?://[^/]*\.([a-z]{2})/", g(r, "Final URL") + "/")
            if m and DG_TLD.get(m.group(1)):
                k["trg"] = DG_TLD[m.group(1)]
            if len(k["primeri"]) < 3 and g(r, "Headline 1"):
                k["primeri"].append({"naslovi": [g(r, f"Headline {i}") for i in range(1, 6) if g(r, f"Headline {i}")],
                                     "opisi": [g(r, f"Description {i}") for i in range(1, 6) if g(r, f"Description {i}")]})
    return [k for k in kamp.values() if (k["tip"] or "").lower().startswith("demand gen") or k["ad_groups"]]


def vklopi(G: dict):
    app, DATA_DIR = G["app"], G["DATA_DIR"]
    _jload, _jsave, _lj_iso = G["_jload"], G["_jsave"], G["_lj_iso"]
    from fastapi import Request, UploadFile, File, Form
    from fastapi.responses import FileResponse, JSONResponse, Response

    NAST_FILE = DATA_DIR / "gads_dg.json"          # {trgi: {trg: {racun, kampanje: {ime: {...}}, izbrana}}}
    PAK_FILE = DATA_DIR / "gads_dg_paketi.json"    # {paketi: [...]} (zadnjih 30)
    SLIKE_DIR = DATA_DIR / "gads_dg"
    lock = asyncio.Lock()

    def prijava(request) -> bool:
        return G["_auth_check_token"](request.cookies.get(G["AUTH_COOKIE"], ""))

    def ni():
        return JSONResponse({"ok": False, "error": "Prijavi se."}, status_code=403)

    @app.get("/gads-dg")
    async def dg_stran(request: Request):
        return FileResponse("static/gads_dg.html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    @app.get("/gads-dg/api/nastavitve")
    async def dg_nastavitve(request: Request):
        if not prijava(request):
            return ni()
        d = _jload(NAST_FILE, {}) or {}
        trgi = d.get("trgi") or {}
        for t, tt in trgi.items():   # 📒 + SKU-ji iz izvoženih paketov (varnost: zapis v evidenco se je lahko izgubil)
            tt["narejeni"] = narejeni_trga(tt, t)
        return {"ok": True, "trgi": trgi, "jeziki": DG_JEZIK, "stat": statistika(d)}

    def narejeni_trga(tt, trg):
        """Evidenca narejenih na trgu = zapisi narejeni + SKU-ji vseh kampanj trga + SKU-ji IZVOŽENIH paketov trga (zgodovina).
        2026-10-18: PANMAX je bil v izvoženem paketu SL, a ga evidenca ni imela (zapis izgubljen — npr. dva procesa ob deployu
        ali prepis kampanje ob uvozu iz Editorja) → zgodovina paketov je zanesljiv vir."""
        nar = dict(tt.get("narejeni") or {})
        for kn, kv in (tt.get("kampanje") or {}).items():
            for s_ in kv.get("skuji") or []:
                nar.setdefault(s_, {"kampanja": kn, "at": kv.get("uvoz_at"), "vir": "izvoz"})
        for pk in pak_load()["paketi"]:
            if pk.get("trg") != trg or not pk.get("izvozeno"):
                continue
            for x in pk.get("postavke") or []:
                if x.get("status") == "ok" and x.get("vkljuci") is not False and x.get("sku"):
                    nar.setdefault(x["sku"].upper(), {"kampanja": pk.get("kampanja"), "ad_group": x.get("ad_group"), "at": pk.get("izvozeno"),
                                                      "vir": "paket", "pid": pk.get("id")})
        return nar

    def statistika(d):
        """📊 Števec: oglasi (SKU-ji, izvoženi prek Suban) in nove kampanje — danes / skupaj / po trgih + zadnjih 14 dni."""
        danes = _lj_iso()[:10]
        po_trgih, dnevi, kamp = {}, {}, {}
        for t, tt in (d.get("trgi") or {}).items():
            s = po_trgih.setdefault(t, {"oglasi": 0, "danes": 0, "kampanje": 0, "vsi": len(tt.get("narejeni") or {})})
            for sku, z in (tt.get("narejeni") or {}).items():
                if z.get("vir") != "suban":
                    continue
                dan = str(z.get("at") or "")[:10]
                s["oglasi"] += 1
                s["danes"] += dan == danes
                dnevi[dan] = dnevi.get(dan, 0) + 1
            for ime, k in (tt.get("kampanje") or {}).items():
                if k.get("iz_suban"):
                    kamp[(t, ime)] = str(k.get("ustvarjena") or k.get("uvoz_at") or "")[:10]
        for p in pak_load()["paketi"]:
            if p.get("nova_kampanja") and p.get("izvozeno"):
                kamp.setdefault((p["trg"], p["kampanja"]), str(p["izvozeno"])[:10])
        for (t, _), dan in kamp.items():
            po_trgih.setdefault(t, {"oglasi": 0, "danes": 0, "kampanje": 0, "vsi": 0})["kampanje"] += 1
        od = (datetime.strptime(danes, "%Y-%m-%d") - timedelta(days=13))
        zad14 = [{"d": (od + timedelta(days=i)).strftime("%Y-%m-%d"), "n": dnevi.get((od + timedelta(days=i)).strftime("%Y-%m-%d"), 0)} for i in range(14)]
        return {"danes": {"oglasi": sum(s["danes"] for s in po_trgih.values()), "kampanje": sum(1 for v in kamp.values() if v == danes)},
                "skupaj": {"oglasi": sum(s["oglasi"] for s in po_trgih.values()), "kampanje": len(kamp),
                           "trgi": sum(1 for s in po_trgih.values() if s["oglasi"] or s["kampanje"])},
                "po_trgih": po_trgih, "dnevi": zad14}

    @app.post("/gads-dg/api/uvoz")
    async def dg_uvoz(request: Request, file: UploadFile = File(...), trg: str = Form("")):
        """Izvoz ene ali več kampanj iz Google Ads Editorja (CSV, UTF-16/UTF-8, TAB) → nastavitve trga."""
        if not prijava(request):
            return ni()
        raw = await file.read()
        try:
            kamp = beri_izvoz(raw)
        except Exception as e:
            return {"ok": False, "error": f"Datoteke ni mogoče prebrati ({e}) — izvozi CSV iz Google Ads Editorja."}
        if not kamp:
            return {"ok": False, "error": "V datoteki ni Demand Gen kampanje."}
        ime = file.filename or ""
        racun = ime.split("++")[0].strip() if "++" in ime else ""
        async with lock:
            d = _jload(NAST_FILE, {}) or {}
            trgi = d.setdefault("trgi", {})
            nove = []
            for k in kamp:
                t = (trg or k["trg"] or "").lower()
                if t not in DG_JEZIK:
                    continue
                if k["trg"] and trg and k["trg"] != trg:
                    return {"ok": False, "error": f"Kampanja »{k['ime']}« ima URL-je trga {k['trg'].upper()}, izbran pa je {trg.upper()} — preveri izvoz."}
                tt = trgi.setdefault(t, {"racun": "", "kampanje": {}, "izbrana": ""})
                if racun:
                    tt["racun"] = racun
                k["uvoz_at"] = _lj_iso()
                star = tt["kampanje"].get(k["ime"]) or {}
                for f_ in ("iz_suban", "iz_paketa", "ag_paket"):   # ponoven uvoz iz Editorja ohrani, da jo je ustvaril Suban (števec)
                    if star.get(f_):
                        k[f_] = star[f_]
                if star.get("iz_suban"):
                    k["ustvarjena"] = star.get("ustvarjena") or star.get("uvoz_at")
                tt["kampanje"][k["ime"]] = k
                tt["izbrana"] = tt.get("izbrana") or k["ime"]
                nar = tt.setdefault("narejeni", {})   # 📒 evidenca narejenih SKU-jev na trgu (tudi ročni oglasi iz izvoza)
                for ag in k["ad_groups"]:
                    m_ = re.search(r"SKU:\s*([A-Za-z0-9_\-\.]+)", ag)
                    if m_ and m_.group(1).upper() not in nar:
                        nar[m_.group(1).upper()] = {"kampanja": k["ime"], "ad_group": ag, "at": k["uvoz_at"], "vir": "izvoz"}
                nove.append({"trg": t, "kampanja": k["ime"], "ad_groups": len(k["ad_groups"]), "skuji": len(k["skuji"])})
            if not nove:
                return {"ok": False, "error": "Trga ni bilo mogoče določiti (ni Final URL) — izberi trg ročno in naloži znova."}
            _jsave(NAST_FILE, d)
        return {"ok": True, "nove": nove, "trgi": d["trgi"]}

    # ── priprava paketa (v ozadju; Cloudflare prekine dolge zahteve) ──
    def pak_load():
        return _jload(PAK_FILE, {"paketi": []}) or {"paketi": []}

    async def pak_set(pid, fn):
        async with lock:
            d = pak_load()
            p = next((x for x in d["paketi"] if x["id"] == pid), None)
            if p is not None:
                fn(p)
                p["spremenjeno"] = _lj_iso()   # ⏱ zadnji napredek (zataknjen paket po ponovnem zagonu strežnika)
                _jsave(PAK_FILE, d)

    def zastalo(p, minut=10):
        """Paket »v delu«, ki se > minut ne premakne = opravilo v ozadju se je izgubilo (ponovni zagon strežnika / deploy)."""
        if p.get("status") != "v_delu":
            return False
        try:
            t = datetime.fromisoformat(str(p.get("spremenjeno") or p.get("at"))[:19])
            return (datetime.fromisoformat(_lj_iso()[:19]) - t).total_seconds() > minut * 60
        except ValueError:
            return False

    def najdi_izdelek(rows, sku):
        u = sku.strip().upper()
        for r in rows:
            if (r.get("sku") or "").upper() == u or (r.get("nc_sku") or "").upper() == u:
                return r
        for r in rows:
            if u in re.split(r"[-/\s]+", (r.get("sku") or "").upper()):
                return r
        return None

    def slika_fit(raw: bytes, w: int, h: int) -> bytes:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        r0, r1 = im.width / im.height, w / h
        if abs(r0 - r1) / r1 <= 0.18:   # skoraj pravo razmerje → izrez sredine
            if r0 > r1:
                nw = int(im.height * r1); x = (im.width - nw) // 2; im = im.crop((x, 0, x + nw, im.height))
            else:
                nh = int(im.width / r1); y = (im.height - nh) // 2; im = im.crop((0, y, im.width, y + nh))
            im = im.resize((w, h))
        else:                            # sicer celoten izdelek na belo ozadje (nič odrezanega)
            im.thumbnail((w, h)); c = Image.new("RGB", (w, h), (255, 255, 255)); c.paste(im, ((w - im.width) // 2, (h - im.height) // 2)); im = c
        b = io.BytesIO(); im.save(b, format="JPEG", quality=90); return b.getvalue()

    async def pripravi_slike(pid, sku, urls):
        import httpx
        mapa = SLIKE_DIR / pid / sku
        mapa.mkdir(parents=True, exist_ok=True)
        out = []
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as hc:
            for i, u in enumerate(urls[:4]):
                try:
                    r = await hc.get(u)
                    if r.status_code != 200:
                        continue
                    vrste = ["1x1"] + (["191x1"] if i < 2 else []) + (["4x5"] if i == 0 else [])
                    for v in vrste:
                        w, h = DG_SLIKE[v]
                        fn = f"{sku}_{v}_{i + 1}.jpg"
                        (mapa / fn).write_bytes(await asyncio.to_thread(slika_fit, r.content, w, h))
                        out.append({"vrsta": v, "datoteka": fn})
                except Exception as e:
                    print(f"[gads-dg] slika {sku} {u[:60]}: {e}")
        return out

    # 🎨 načrt AI slik na SKU: (vrsta, razmerje za Gemini, indeks vibe) — Google priporoča ≥ 3 pokončne
    DG_AI_NACRT = [("1x1", "1:1", 0), ("1x1", "1:1", 1), ("4x5", "4:5", 0), ("4x5", "4:5", 1), ("4x5", "4:5", 2), ("191x1", "16:9", 0), ("191x1", "16:9", 2)]
    gem_sem = asyncio.Semaphore(20)   # vzporednih klicev Gemini (vse SKU-je skupaj) — ⚡ 2026-10-22: 6 → 12, 2026-10-25: 12 → 20

    def kratek_napis(b, n=20):
        """Napis na sliki: do ~20 znakov (daljši se na slikah ne berejo); krajše ostane cele (»2 в 1«),
        daljše skrajša na cele besede in ne konča z veznikom/predlogom (»Мокро и сухо почистване …« → »Мокро и сухо«)."""
        t = " ".join(str(b).strip().rstrip(".!").split())
        if len(t) <= n:
            return t
        out = []
        for x in t.split():
            if len(" ".join(out + [x])) > n:
                break
            out.append(x)
        while len(out) > 1 and len(out[-1]) <= 3:
            out.pop()
        return " ".join(out) or t[:n]

    def kreativa_prompt(trg, ime, bullets, vibe, razmerje):
        jez = DG_JEZIK[trg]
        oblika = {"1:1": "Square 1:1", "4:5": "Vertical portrait 4:5", "16:9": "Wide horizontal format (it will be cropped to 1.91:1, so keep ALL text and the product inside the central horizontal band)"}[razmerje]
        return (f"From these reference images create a new high-converting e-commerce ad creative (Google Ads / Facebook) for the product {ime.upper()}. "
                "Keep the product EXACTLY as in the reference images — same shape, colours, parts and details; never invent a different product. "
                f"Background / scene: a more intense '{vibe}' look that sells the benefit. "
                f"On-image text ONLY in {jez} (correct spelling, exactly these words): the product name '{ime.upper()}' in capital letters "
                f"(you may style it as a small logo), and 3 very short benefit labels (1–2 words each, big and readable), each with a simple icon: " + " · ".join(f"\"{kratek_napis(b)}\"" for b in bullets[:3]) + ". "
                "No prices, no discounts, no other words, no watermarks. Keep all text and icons well inside the image, at least 8% away from every edge — "
                f"nothing may be cut off. {oblika} format.")

    def ai_obrez(raw: bytes, vrsta: str) -> bytes:
        """Gemini razmerje → točne mere Google Ads (16:9 → izrez sredine na 1,91:1)."""
        from PIL import Image
        w, h = DG_SLIKE[vrsta]
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        r0, r1 = im.width / im.height, w / h
        if r0 > r1 + 0.01:
            nw = int(im.height * r1); x = (im.width - nw) // 2; im = im.crop((x, 0, x + nw, im.height))
        elif r0 < r1 - 0.01:
            nh = int(im.width / r1); y = (im.height - nh) // 2; im = im.crop((0, y, im.width, y + nh))
        im = im.resize((w, h))
        b = io.BytesIO(); im.save(b, format="JPEG", quality=90); return b.getvalue()

    async def gemini_slika(refs, prompt, razmerje):
        """NB2.1 (GEMINI_FLASH_IMG; ob napaki stari NB2 do ukinitve). Vrne bajte slike ali None."""
        import httpx, base64, os
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY ni nastavljen")
        parts = [{"inline_data": {"mime_type": m, "data": base64.b64encode(b).decode()}} for b, m in refs] + [{"text": prompt}]
        modeli = [G.get("GEMINI_FLASH_IMG") or "gemini-nano-banana-2.1"]
        if G.get("GEMINI_FLASH_IMG_STARI") and G["GEMINI_FLASH_IMG_STARI"] not in modeli:
            modeli.append(G["GEMINI_FLASH_IMG_STARI"])
        zadnja = ""
        async with gem_sem:
            async with httpx.AsyncClient(timeout=150) as hc:
                for model in modeli:
                    for cfg in ({"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": razmerje}}, {"responseModalities": ["IMAGE", "TEXT"]}):
                        try:
                            for pos in range(4):   # 429 / 5xx → počakaj in ponovi (višja vzporednost)
                                r = await hc.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                                                  json={"contents": [{"parts": parts}], "generationConfig": cfg})
                                j = r.json()
                                if r.status_code not in (429, 500, 502, 503) or pos == 3:
                                    break
                                await asyncio.sleep(6 * (pos + 1))
                        except Exception as e:
                            zadnja = str(e)[:150]; continue
                        if r.status_code != 200:
                            zadnja = str((j.get("error") or {}).get("message") or j)[:150]
                            continue
                        try:
                            G["_ai_log_gemini"](model, j, "google_ads_dg")
                        except Exception:
                            pass
                        for c in j.get("candidates") or []:
                            for pt in (c.get("content") or {}).get("parts") or []:
                                if "inlineData" in pt:
                                    return base64.b64decode(pt["inlineData"].get("data") or "")
                        zadnja = "Gemini ni vrnil slike"
        raise RuntimeError(zadnja or "napaka Gemini")

    async def pripravi_ai_slike(pid, sku, urls, ime, bullets, vibes, trg):
        import httpx
        mapa = SLIKE_DIR / pid / sku
        mapa.mkdir(parents=True, exist_ok=True)
        refs = []
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as hc:
            for u in urls[:3]:   # do 3 referenčne slike izdelka (enako kot Kreative: zvestoba izdelka)
                try:
                    r = await hc.get(u)
                    if r.status_code == 200 and r.content:
                        refs.append((r.content, (r.headers.get("content-type") or "image/jpeg").split(";")[0]))
                except Exception as e:
                    print(f"[gads-dg] ref {sku}: {e}")
        if not refs:
            return [], ["ni referenčnih slik"]
        vibes = [v for v in (vibes or []) if v] or ["clean bright lifestyle", "in-use moment", "premium studio"]
        while len(vibes) < 3:
            vibes.append(vibes[-1])
        bullets = [b for b in (bullets or []) if b][:3]

        async def ena(i, vrsta, razm, vi):
            try:
                raw = await gemini_slika(refs, kreativa_prompt(trg, ime, bullets, vibes[vi], razm), razm)
                fn = f"{sku}_{vrsta}_ai{i + 1}.jpg"
                (mapa / fn).write_bytes(await asyncio.to_thread(ai_obrez, raw, vrsta))
                return {"vrsta": vrsta, "datoteka": fn, "ai": True, "vibe": vibes[vi]}, None
            except Exception as e:
                return None, f"{vrsta}: {str(e)[:100]}"
        rez = await asyncio.gather(*(ena(i, v, r_, vi) for i, (v, r_, vi) in enumerate(DG_AI_NACRT)))
        return [x for x, _ in rez if x], [e for _, e in rez if e]

    def beri_json(raw):
        """Prvi/največji veljaven JSON objekt v besedilu (raw_decode od vsakega »{« — besedilo pred/za JSON ne moti)."""
        dec, naj = json.JSONDecoder(), {}
        for i, ch in enumerate(raw):
            if ch == "{":
                try:
                    o, _ = dec.raw_decode(raw, i)
                except ValueError:
                    continue
                if isinstance(o, dict) and len(json.dumps(o)) > len(json.dumps(naj)):
                    naj = o
        return naj

    def ai_besedila(trg, naziv, opis, primeri):
        jez = DG_JEZIK[trg]
        prim = "\n".join("- headlines: " + " | ".join(p["naslovi"]) + "\n  descriptions: " + " | ".join(p["opisi"]) for p in (primeri or [])[:2])
        prompt = (
            f"You write Google Ads Demand Gen image ad copy for an e-commerce shop (Maaarket). Language: {jez} ONLY (native, natural, correct grammar).\n"
            f"Product name (shop title): {naziv}\nProduct description (may be another language — use its meaning): {opis[:1500]}\n"
            + (f"Existing ads in this campaign (match the tone and style, do not copy):\n{prim}\n" if prim else "")
            + "Write:\n"
            "- kratko_ime: the short distinctive product name as used in the title (e.g. 'BarrierWater', 'OrtoFeet'), Latin letters, max 25 chars.\n"
            f"- 5 headlines, each MAX {DG_MAX['headline']} characters (count carefully, spaces included): product name + main benefit, problem/solution, "
            "use case, key feature — all different, no repetition.\n"
            f"- 5 descriptions, each MAX {DG_MAX['description']} characters: concrete benefits and use, each different.\n"
            f"- bullets: 3 ULTRA short selling callouts for ON THE IMAGE, in {jez}: 1–2 words each, MAX 14 characters (e.g. 'Без кабели', '2 в 1', 'Лесен монтаж') — a punchy label, never a sentence.\n"
            "- vibes: 3 short background/scene concepts for ad images, in English, max 4 words each, specific to this product (e.g. 'sunny kitchen in use', 'before/after floor', 'premium dark studio').\n"
            "Rules (Google Ads policy): no prices, no discounts or '1+1 free' unless clearly stated in the title, no 'best/#1' claims, no medical or "
            "guaranteed claims, no ALL CAPS words, max one exclamation mark in total, no emojis, no phone numbers or URLs.\n"
            'Return ONLY JSON: {"kratko_ime": "...", "naslovi": ["...", "...", "...", "...", "..."], "opisi": ["...", "...", "...", "...", "..."], '
            '"bullets": ["...", "...", "..."], "vibes": ["...", "...", "..."]}')
        msg = G["client"].messages.create(model="claude-sonnet-4-6", max_tokens=6000, messages=[{"role": "user", "content": prompt}])
        raw = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        j = beri_json(raw)   # 2026-10-22: »Extra data« — model je za JSON dodal še besedilo / drug JSON (GR, 2 SKU)
        skrajsaj = lambda s, n: s if len(s) <= n else (s[:n].rsplit(" ", 1)[0] if " " in s[:n] else s[:n]).rstrip(" ,.;:-")
        nas = [skrajsaj(str(x).strip(), DG_MAX["headline"]) for x in (j.get("naslovi") or []) if str(x).strip()][:5]
        opi = [skrajsaj(str(x).strip(), DG_MAX["description"]) for x in (j.get("opisi") or []) if str(x).strip()][:5]
        bul = [kratek_napis(x) for x in (j.get("bullets") or []) if str(x).strip()][:3]
        vib = [str(x).strip()[:40] for x in (j.get("vibes") or []) if str(x).strip()][:3]
        return str(j.get("kratko_ime") or "").strip()[:25], nas, opi, bul, vib

    async def obdelaj(pid, trg, kampanja, skus, ai_slike=True):
        try:
            res = await G["_marza_trgi_get"](trg)
            rows = (res or {}).get("rows") or []
        except Exception as e:
            rows = []
            print(f"[gads-dg] marža {trg}: {e}")
        feed = G["feed_by_lang"].get(trg) or {}
        sl = G["feed_by_lang"].get("sl") or {}
        kinfo = ((_jload(NAST_FILE, {}) or {}).get("trgi", {}).get(trg, {}).get("kampanje", {}).get(kampanja) or {})   # kampanja = izvorna (vir)
        sem = asyncio.Semaphore(6)   # ⚡ SKU-jev hkrati (besedila Sonnet + 7 slik NB2.1) — prej 4

        async def en(sku):
            async with sem:
                post = {"sku": sku, "status": "napaka", "napake": [], "opozorila": []}
                r = najdi_izdelek(rows, sku)
                if not r:
                    post["napake"].append("SKU ni v feedu trga " + trg.upper())
                else:
                    it = feed.get(str(r.get("g_id"))) or {}
                    opis = it.get("description") or (sl.get(str(r.get("cms_id") or "")) or {}).get("description") or ""
                    post.update({"naziv": r.get("naziv") or it.get("title") or "", "url": r.get("url") or it.get("url") or "", "g_id": str(r.get("g_id") or "")})
                    slike_url = it.get("all_images") or ([r.get("slika")] if r.get("slika") else [])
                    try:
                        kr, nas, opi, bul, vib = await asyncio.to_thread(ai_besedila, trg, post["naziv"], opis, kinfo.get("primeri"))
                    except Exception as e:
                        kr, nas, opi, bul, vib = "", [], [], [], []
                        post["napake"].append(f"AI besedila: {str(e)[:120]}")
                    ime = kr or (post["naziv"].split(",")[0][:25])
                    slike, nap_sl = [], []
                    if ai_slike:   # 🎨 NB2.1 kreative (ime + 3 prednosti z ikonami + ozadje, besedilo v jeziku trga)
                        slike, nap_sl = await pripravi_ai_slike(pid, sku, slike_url, ime, bul or nas[:3], vib, trg)
                        if nap_sl:
                            post["opozorila"].append("AI slike: " + "; ".join(nap_sl[:3]))
                    if not slike:   # brez AI ali AI ni uspel → galerija feeda (izrez / bela podlaga)
                        slike = await pripravi_slike(pid, sku, slike_url)
                    post.update({"kratko_ime": ime, "ad_group": f"{ime}, SKU: {sku}", "ad_name": ime, "naslovi": nas, "opisi": opi,
                                 "bullets": bul, "vibes": vib, "slike": slike, "vkljuci": True, "status": "ok"})
                await pak_set(pid, lambda p: p["postavke"].__setitem__(next(i for i, x in enumerate(p["postavke"]) if x["sku"] == sku), post))

        async def en_varno(sku):
            try:
                await en(sku)
            except Exception as e:   # nobena napaka ne sme pustiti postavke »v pripravi«
                print(f"[gads-dg] {sku}: {e}")
                napaka = {"sku": sku, "status": "napaka", "napake": [f"priprava ni uspela: {str(e)[:150]}"], "opozorila": []}
                await pak_set(pid, lambda p: p["postavke"].__setitem__(next(i for i, x in enumerate(p["postavke"]) if x["sku"] == sku), napaka))

        try:
            await asyncio.gather(*(en_varno(s) for s in skus))
        finally:
            await pak_set(pid, lambda p: p.update(status="pripravljeno", konec=_lj_iso()))

    @app.post("/gads-dg/api/pripravi")
    async def dg_pripravi(request: Request, data: dict):
        if not prijava(request):
            return ni()
        trg = str(data.get("trg") or "").lower()
        kampanja = str(data.get("kampanja") or "").strip()
        _kz = ((((_jload(NAST_FILE, {}) or {}).get("trgi") or {}).get(str(data.get("trg") or "").lower()) or {}).get("kampanje") or {})
        if kampanja and kampanja not in _kz:   # ime z dvojnim presledkom (Editor) — izbirnik ga je strnil v enega
            kampanja = next((n for n in _kz if " ".join(n.split()) == " ".join(kampanja.split())), kampanja)
        skus = []
        for s in re.split(r"[\s,;]+", str(data.get("skus") or "")):
            s = s.strip().upper()
            if s and s not in skus:
                skus.append(s)
        skus = skus[:200]
        if trg not in DG_JEZIK or not kampanja or not skus:
            return {"ok": False, "error": "Izberi trg, kampanjo in vpiši vsaj en SKU."}
        nova = data.get("nova") if isinstance(data.get("nova"), dict) else None
        tt = ((_jload(NAST_FILE, {}) or {}).get("trgi") or {}).get(trg) or {}
        if nova:   # ➕ nova kampanja = kopija nastavitev izbrane (vir), z novim imenom, proračunom, Target CPA; Paused
            ime_n = str(nova.get("ime") or "").strip()
            if not ime_n:
                return {"ok": False, "error": "Vpiši ime nove kampanje."}
            if ime_n in (tt.get("kampanje") or {}):
                return {"ok": False, "error": f"Kampanja »{ime_n}« že obstaja — izberi drugo ime (uvoz bi jo SPREMENIL)."}
            if not ((tt.get("kampanje") or {}).get(kampanja) or {}).get("kamp_vrstica"):
                return {"ok": False, "error": "Izvorna kampanja nima nastavitev — naloži njen izvoz znova (vključno z vrstico kampanje)."}
            try:
                bud = round(float(str(nova.get("budget") or "").replace(",", ".")), 2)
                tcpa = round(float(str(nova.get("tcpa") or "").replace(",", ".")), 2)
            except ValueError:
                return {"ok": False, "error": "Proračun in Target CPA morata biti številki."}
            if bud <= 0 or tcpa <= 0:
                return {"ok": False, "error": "Proračun in Target CPA morata biti večja od 0."}
            nova = {"ime": ime_n, "vir": kampanja, "budget": bud, "tcpa": tcpa}
        # 📒 že narejeni na tem trgu (evidenca + SKU-ji vseh kampanj trga) → preskoči, razen če »tudi že narejene«
        nar = narejeni_trga(tt, trg)
        preskoceni = []
        if not data.get("tudi_narejene"):
            for s_ in skus:
                if s_ in nar:
                    preskoceni.append({"sku": s_, "kampanja": nar[s_].get("kampanja"), "at": str(nar[s_].get("at") or "")[:10], "ad_group": nar[s_].get("ad_group")})
            skus = [s_ for s_ in skus if s_ not in nar]
        if not skus:
            return {"ok": False, "preskoceni": preskoceni,
                    "error": "Vsi SKU-ji so na tem trgu že narejeni: " + ", ".join(f"{x['sku']} ({x['at']}, {x['kampanja']})" for x in preskoceni) + " — označi »Tudi že narejene«, če jih želiš znova."}
        pid = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
        async with lock:
            d = pak_load()
            d["paketi"].insert(0, {"id": pid, "trg": trg, "kampanja": nova["ime"] if nova else kampanja, "vir_kampanja": kampanja,
                                   "nova_kampanja": nova, "status": "v_delu", "at": _lj_iso(), "preskoceni": preskoceni,
                                   "postavke": [{"sku": s, "status": "caka"} for s in skus]})
            d["paketi"] = d["paketi"][:30]
            _jsave(PAK_FILE, d)
        await pak_set(pid, lambda q: q.update(ai_slike=data.get("ai_slike", True) is not False))
        asyncio.create_task(obdelaj(pid, trg, kampanja, skus, data.get("ai_slike", True) is not False))   # besedila v slogu izvorne kampanje
        return {"ok": True, "id": pid, "preskoceni": preskoceni}

    def validiraj(p, nast):
        kamp_t = nast.get("trgi", {}).get(p["trg"], {}).get("kampanje", {})
        kinfo = kamp_t.get(p.get("vir_kampanja") or p["kampanja"]) or {}
        if p.get("nova_kampanja"):   # nova kampanja: brez obstoječih skupin; ime ne sme obstajati (razen če jo je ustvaril ta paket)
            obst_ag, obst_sku = set(), set()
            if p["kampanja"] in kamp_t and kamp_t[p["kampanja"]].get("iz_paketa") != p["id"]:
                for x in p["postavke"]:
                    if "kampanja s tem imenom že obstaja" not in (x.get("napake") or []):
                        x.setdefault("napake", []).append("kampanja s tem imenom že obstaja")
        else:
            agp = kinfo.get("ag_paket") or {}   # skupine, ki jih je izvozil TA paket, niso dvojniki
            obst_ag = {x.lower() for x in kinfo.get("ad_groups") or [] if agp.get(x.lower()) != p["id"]}
            obst_sku = {s_ for s_ in (kinfo.get("skuji") or []) if not any(v == p["id"] and ("sku: " + s_.lower()) in a for a, v in agp.items())}
        bn = kinfo.get("business_name") or ("Maaarket." + {"sl": "si"}.get(p["trg"], p["trg"]))
        vidjena = set()
        for x in p["postavke"]:
            x["napake"] = [n for n in (x.get("napake") or []) if n.startswith("SKU ni") or n.startswith("AI") or n.startswith("priprava") or n.startswith("kampanja s tem")]
            x["opozorila"] = [o for o in (x.get("opozorila") or []) if o.startswith("AI slike")]
            if x.get("status") != "ok":
                continue
            if not x.get("ad_group"):
                x["napake"].append("ni imena oglasne skupine")
            elif x["ad_group"].lower() in obst_ag:
                x["napake"].append("oglasna skupina s tem imenom že obstaja v kampanji (uvoz bi jo SPREMENIL)")
            if x["ad_group"].lower() in vidjena:
                x["napake"].append("isto ime skupine je v paketu dvakrat")
            vidjena.add(x["ad_group"].lower())
            if x["sku"] in obst_sku:
                x["opozorila"].append("SKU že ima oglasno skupino v tej kampanji")
            nas = [s for s in x.get("naslovi") or [] if s.strip()]
            opi = [s for s in x.get("opisi") or [] if s.strip()]
            if not nas:
                x["napake"].append("ni naslova")
            if not opi:
                x["napake"].append("ni opisa")
            x["napake"] += [f"naslov {i + 1} ima {len(s)} znakov (največ {DG_MAX['headline']})" for i, s in enumerate(nas) if len(s) > DG_MAX["headline"]]
            x["napake"] += [f"opis {i + 1} ima {len(s)} znakov (največ {DG_MAX['description']})" for i, s in enumerate(opi) if len(s) > DG_MAX["description"]]
            if not x.get("url"):
                x["napake"].append("ni Final URL")
            if not any(s["vrsta"] in ("1x1", "191x1") and not s.get("izkl") for s in x.get("slike") or []):
                x["opozorila"].append("ni slike 1:1 ali 1,91:1 — dodaj jo v Editorju")
        return bn, kinfo

    @app.post("/gads-dg/api/nove-slike")
    async def dg_nove_slike(request: Request, data: dict):
        """🎨 Samo nove AI kreative (NB2.1) za obstoječi paket — besedila ostanejo. {id, skus?: [...]} (prazno = vsi)."""
        if not prijava(request):
            return ni()
        pid = str(data.get("id") or "")
        p = next((x for x in pak_load()["paketi"] if x["id"] == pid), None)
        if not p:
            return {"ok": False, "error": "Paketa ni."}
        izb = {str(x).upper() for x in (data.get("skus") or [])}
        cilj = [x for x in p["postavke"] if x.get("status") == "ok" and (not izb or x["sku"] in izb)]
        if not cilj:
            return {"ok": False, "error": "V paketu ni pripravljenih SKU-jev."}
        feed = G["feed_by_lang"].get(p["trg"]) or {}
        await pak_set(pid, lambda q: q.update(status="v_delu"))
        for x in cilj:
            sku = x["sku"]
            await pak_set(pid, lambda q, sku=sku: next(y for y in q["postavke"] if y["sku"] == sku).update(slike_v_delu=True))

        async def delaj():
            async def en(x):
                try:
                    it = feed.get(str(x.get("g_id") or "")) or {}
                    urls = it.get("all_images") or []
                    sl, nap = await pripravi_ai_slike(pid, x["sku"], urls, x.get("kratko_ime") or x.get("ad_name") or x["sku"],
                                                      x.get("bullets") or (x.get("naslovi") or [])[:3], x.get("vibes") or [], p["trg"])
                except Exception as e:
                    sl, nap = [], [str(e)[:120]]

                def upd(q):
                    y = next(y for y in q["postavke"] if y["sku"] == x["sku"])
                    y.pop("slike_v_delu", None)
                    y["opozorila"] = [o for o in (y.get("opozorila") or []) if not o.startswith("AI slike")] + (["AI slike: " + "; ".join(nap[:3])] if nap else [])
                    if sl:
                        y["slike"] = sl
                await pak_set(pid, upd)
            try:
                await asyncio.gather(*(en(x) for x in cilj))
            finally:
                await pak_set(pid, lambda q: q.update(status="pripravljeno"))
        asyncio.create_task(delaj())
        return {"ok": True, "n": len(cilj)}

    @app.get("/gads-dg/api/paket/{pid}")
    async def dg_paket(request: Request, pid: str):
        if not prijava(request):
            return ni()
        p = next((x for x in pak_load()["paketi"] if x["id"] == pid), None)
        if not p:
            return {"ok": False, "error": "Paketa ni."}
        bn, kinfo = validiraj(p, _jload(NAST_FILE, {}) or {})
        return {"ok": True, "paket": p, "business_name": bn, "kampanja_najdena": bool(kinfo), "zastalo": zastalo(p)}

    @app.post("/gads-dg/api/nadaljuj")
    async def dg_nadaljuj(request: Request, data: dict):
        """▶ Nadaljuj zataknjene: ponovno požene samo postavke, ki so ostale »v pripravi« (opravilo se je izgubilo ob ponovnem zagonu)."""
        if not prijava(request):
            return ni()
        pid = str(data.get("id") or "")
        p = next((x for x in pak_load()["paketi"] if x["id"] == pid), None)
        if not p:
            return {"ok": False, "error": "Paketa ni."}
        if not zastalo(p, 8):
            return {"ok": False, "error": "Paket se še pripravlja — počakaj nekaj minut."}
        skus = [x["sku"] for x in p.get("postavke") or [] if x.get("status") == "caka"]
        if not skus:
            await pak_set(pid, lambda q: q.update(status="pripravljeno"))
            return {"ok": True, "n": 0}
        await pak_set(pid, lambda q: q.update(status="v_delu"))
        asyncio.create_task(obdelaj(pid, p["trg"], p.get("vir_kampanja") or p["kampanja"], skus, p.get("ai_slike", True) is not False))
        return {"ok": True, "n": len(skus)}

    @app.get("/gads-dg/api/paketi")
    async def dg_paketi(request: Request):
        if not prijava(request):
            return ni()
        return {"ok": True, "paketi": [{k: p.get(k) for k in ("id", "trg", "kampanja", "status", "at", "izvozeno")} | {"n": len(p.get("postavke") or []),
                "skuji": [x.get("sku") for x in (p.get("postavke") or [])][:12], "nova": bool(p.get("nova_kampanja"))} for p in pak_load()["paketi"]]}

    @app.post("/gads-dg/api/shrani")
    async def dg_shrani(request: Request, data: dict):
        """Ročni popravki iz pregleda: ime skupine, ime oglasa, naslovi, opisi, vključi."""
        if not prijava(request):
            return ni()
        pid, nove = str(data.get("id") or ""), {str(x.get("sku")): x for x in (data.get("postavke") or []) if isinstance(x, dict)}

        def upd(p):
            for x in p["postavke"]:
                n = nove.get(x["sku"])
                if not n or x.get("status") != "ok":
                    continue
                for k in ("ad_group", "ad_name"):
                    if k in n:
                        x[k] = str(n[k]).strip()[:255]
                for k in ("naslovi", "opisi"):
                    if isinstance(n.get(k), list):
                        x[k] = [str(s).strip() for s in n[k]][:5]
                if "vkljuci" in n:
                    x["vkljuci"] = bool(n["vkljuci"])
                if isinstance(n.get("slike_izkl"), list):   # 🖼 klik na sliko = izključi iz izvoza
                    izk = set(map(str, n["slike_izkl"]))
                    for s_ in x.get("slike") or []:
                        s_["izkl"] = s_["datoteka"] in izk
        await pak_set(pid, upd)
        return {"ok": True}

    @app.get("/gads-dg/api/slika/{pid}/{sku}/{fn}")
    async def dg_slika(request: Request, pid: str, sku: str, fn: str):
        if not prijava(request):
            return ni()
        f = SLIKE_DIR / re.sub(r"[^\w]", "", pid) / re.sub(r"[^\w\-\.]", "", sku) / re.sub(r"[^\w\-\.]", "", fn)
        if not f.exists():
            return JSONResponse({"ok": False}, status_code=404)
        return FileResponse(str(f), media_type="image/jpeg")

    @app.get("/gads-dg/api/izvoz/{pid}")
    async def dg_izvoz(request: Request, pid: str, status: str = "Enabled"):
        """status = Enabled (privzeto — vse pregledaš v Subanu) ali Paused, velja za novo kampanjo, skupine in oglase."""
        if not prijava(request):
            return ni()
        ST = "Paused" if str(status).lower().startswith("pause") else "Enabled"
        p = next((x for x in pak_load()["paketi"] if x["id"] == pid), None)
        if not p:
            return JSONResponse({"ok": False, "error": "Paketa ni."}, status_code=404)
        bn, kinfo = validiraj(p, _jload(NAST_FILE, {}) or {})
        izb = [x for x in p["postavke"] if x.get("status") == "ok" and x.get("vkljuci", True) and not x.get("napake")]
        if not izb:
            return JSONResponse({"ok": False, "error": "Ni oglasov brez napak za izvoz."}, status_code=400)
        nk = p.get("nova_kampanja")
        if not nk:   # 🛡 2026-10-25: ime kampanje mora biti TOČNO kot v Editorju — sicer Editor ob uvozu ustvari NOVO (Search) kampanjo
            kamp_t = (((_jload(NAST_FILE, {}) or {}).get("trgi") or {}).get(p["trg"]) or {}).get("kampanje") or {}
            if p["kampanja"] not in kamp_t:
                pravo = next((n for n in kamp_t if " ".join(n.split()) == " ".join(p["kampanja"].split())), None)
                if not pravo:
                    return JSONResponse({"ok": False, "error": f"Kampanje »{p['kampanja']}« ni v naloženem izvozu {p['trg'].upper()} — naloži izvoz iz Editorja znova (sicer bi uvoz ustvaril novo kampanjo)."}, status_code=400)
                p = dict(p, kampanja=pravo)
        k_vr, lok = [], []
        if nk:   # ➕ nova kampanja: kopija vrstice izvorne kampanje (ime, proračun, Target CPA, Paused, začetek danes) + lokacije
            kv = dict(kinfo.get("kamp_vrstica") or {})
            if not kv:
                return JSONResponse({"ok": False, "error": "Izvorna kampanja nima nastavitev — naloži izvoz znova."}, status_code=400)
            for x in ("ID", "Approval Status", "Ad strength", "Comment", "Labels"):
                kv.pop(x, None)
            kv.update({"Campaign": nk["ime"], "Budget": f"{nk['budget']:.2f}", "Target CPA": f"{nk['tcpa']:.2f}",
                       "Campaign Status": ST, "Start Date": _lj_iso()[:10]})
            k_vr = [kv]
            for lv in kinfo.get("lokacije") or []:
                lv = dict(lv); lv.update({"Campaign": nk["ime"], "Campaign Status": ST}); lok.append(lv)
        stolpci = []
        for r_ in k_vr + lok:
            stolpci += [c for c in r_ if c not in stolpci]
        stolpci += [c for c in DG_STOLPCI if c not in stolpci]
        b = io.StringIO()
        w = csv.DictWriter(b, fieldnames=stolpci, delimiter="\t", lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        for r_ in k_vr + lok:
            w.writerow(r_)
        for x in izb:   # vrstica A: nova oglasna skupina · vrstica B: nov oglas — oboje Paused, nobenega stolpca kampanje ali ID
            w.writerow({"Campaign": p["kampanja"], "Ad Group": x["ad_group"], "Ad Group Type": "Standard", "Channels": "All Google channels",
                        "Optimized targeting": "Enabled", "Ad Group Status": ST})
            r = {"Campaign": p["kampanja"], "Ad Group": x["ad_group"], "Ad type": "Demand Gen image ad", "Ad Name": x.get("ad_name") or x["ad_group"],
                 "Business name": bn[:DG_MAX["business"]], "Video generation": "Disabled", "Adaptive layouts": "Enabled",
                 "Final URL": x["url"], "Ad Group Status": ST, "Status": ST}
            for i, s in enumerate([s for s in x.get("naslovi") or [] if s.strip()][:5]):
                r[f"Headline {i + 1}"] = s
            for i, s in enumerate([s for s in x.get("opisi") or [] if s.strip()][:5]):
                r[f"Description {i + 1}"] = s
            w.writerow(r)
        man = io.StringIO(); mw = csv.writer(man); mw.writerow(["SKU", "Ad Group", "Ad Name", "Image Type", "File"])
        rep = io.StringIO(); rw = csv.writer(rep); rw.writerow(["SKU", "Status", "Napake", "Opozorila"])
        zb = io.BytesIO()
        with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("ads.csv", b.getvalue().encode("utf-16"))
            for x in izb:
                for s in [s_ for s_ in (x.get("slike") or []) if not s_.get("izkl")]:
                    f = SLIKE_DIR / pid / x["sku"] / s["datoteka"]
                    if f.exists():
                        z.write(f, f"images/{s['datoteka']}")
                        mw.writerow([x["sku"], x["ad_group"], x.get("ad_name"), {"1x1": "Square 1:1", "191x1": "Landscape 1.91:1", "4x5": "Portrait 4:5"}[s["vrsta"]], f"images/{s['datoteka']}"])
            for x in p["postavke"]:
                rw.writerow([x["sku"], "izvoženo" if x in izb else ("izključeno" if x.get("status") == "ok" and not x.get("napake") else "napaka"),
                             "; ".join(x.get("napake") or []), "; ".join(x.get("opozorila") or [])])
            z.writestr("manifest.csv", "﻿" + man.getvalue())
            z.writestr("validation_report.csv", "﻿" + rep.getvalue())
            z.writestr("NAVODILA.txt", ("" 
                + ("0) NOVA KAMPANJA »" + nk["ime"] + "« (" + ST + ") — v pregledu uvoza mora biti Campaign: Added 1, nobena Updated.\n" if nk else "") +
                "1) Google Ads Editor: Get recent changes.\n"
                "2) Account > Import > From file > ads.csv  (pregled mora pokazati samo ADDED, nobenega UPDATED).\n"
                "3) Account > Import > Import image assets from files > mapa slike (v ZIP: images) — vse slike naenkrat v knjižnico, imena po SKU.\n"
                "4) Pri vsakem oglasu: Images > izberi iz knjižnice (išči po SKU) + Logos > logo Maaarket.\n"
                "5) Preveri vse spremembe, šele nato Post. Status ob uvozu: " + ST + (" — po Post so takoj aktivni.\n" if ST == "Enabled" else ".\n")).encode("utf-8"))
        async with lock:
            d = _jload(NAST_FILE, {}) or {}
            tt = d.setdefault("trgi", {}).setdefault(p["trg"], {"racun": "", "kampanje": {}, "izbrana": ""})
            k = tt["kampanje"].get(p["kampanja"])
            if k is None and nk:   # nova kampanja → v seznam trga (kopija izvorne; ime, proračun, CPA)
                k = json.loads(json.dumps(kinfo or {}))
                k.update({"ime": nk["ime"], "ad_groups": [], "skuji": [], "iz_suban": True, "iz_paketa": pid, "uvoz_at": _lj_iso()})
                kv = k.get("kamp_vrstica") or {}
                kv.update({"Campaign": nk["ime"], "Budget": f"{nk['budget']:.2f}", "Target CPA": f"{nk['tcpa']:.2f}"})
                k["kamp_vrstica"] = kv
                k["lokacije"] = [dict(l, Campaign=nk["ime"]) for l in (k.get("lokacije") or [])]
                tt["kampanje"][nk["ime"]] = k
            if True:
                if k is None:   # kampanja ni (več) v seznamu trga → dodaj jo, da evidenca in dvojniki delujejo
                    k = tt["kampanje"].setdefault(p["kampanja"], {"ime": p["kampanja"], "ad_groups": [], "skuji": [], "uvoz_at": _lj_iso()})
                for x in izb:
                    k.setdefault("ag_paket", {})[x["ad_group"].lower()] = pid
                    if x["ad_group"] not in k.setdefault("ad_groups", []):
                        k["ad_groups"].append(x["ad_group"])
                    if x["sku"] not in k.setdefault("skuji", []):
                        k["skuji"].append(x["sku"])
                tt["izbrana"] = p["kampanja"]
                nar = tt.setdefault("narejeni", {})
                for x in izb:
                    nar[x["sku"]] = {"kampanja": p["kampanja"], "ad_group": x["ad_group"], "at": _lj_iso(), "vir": "suban", "pid": pid}
                _jsave(NAST_FILE, d)
        await pak_set(pid, lambda q: q.update(izvozeno=_lj_iso()))
        ime = f"suban_demandgen_{p['trg'].upper()}_{p['at'][:10]}.zip"
        # ⚡ 2026-10-24: Response z bajti namesto StreamingResponse(BytesIO) — ta je pošiljal ZIP »po vrsticah« (počasen prenos)
        return Response(zb.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{ime}"'})

    print("[gads-dg] modul vklopljen")
