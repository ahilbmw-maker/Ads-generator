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
from datetime import datetime

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
        c = g(r, "Campaign")
        if not c:
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
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

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
        return {"ok": True, "trgi": d.get("trgi") or {}, "jeziki": DG_JEZIK}

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
                tt["kampanje"][k["ime"]] = k
                tt["izbrana"] = tt.get("izbrana") or k["ime"]
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
                _jsave(PAK_FILE, d)

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
            "Rules (Google Ads policy): no prices, no discounts or '1+1 free' unless clearly stated in the title, no 'best/#1' claims, no medical or "
            "guaranteed claims, no ALL CAPS words, max one exclamation mark in total, no emojis, no phone numbers or URLs.\n"
            'Return ONLY JSON: {"kratko_ime": "...", "naslovi": ["...", "...", "...", "...", "..."], "opisi": ["...", "...", "...", "...", "..."]}')
        msg = G["client"].messages.create(model="claude-sonnet-4-6", max_tokens=6000, messages=[{"role": "user", "content": prompt}])
        raw = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        j = json.loads(m.group(0)) if m else {}
        skrajsaj = lambda s, n: s if len(s) <= n else (s[:n].rsplit(" ", 1)[0] if " " in s[:n] else s[:n]).rstrip(" ,.;:-")
        nas = [skrajsaj(str(x).strip(), DG_MAX["headline"]) for x in (j.get("naslovi") or []) if str(x).strip()][:5]
        opi = [skrajsaj(str(x).strip(), DG_MAX["description"]) for x in (j.get("opisi") or []) if str(x).strip()][:5]
        return str(j.get("kratko_ime") or "").strip()[:25], nas, opi

    async def obdelaj(pid, trg, kampanja, skus):
        try:
            res = await G["_marza_trgi_get"](trg)
            rows = (res or {}).get("rows") or []
        except Exception as e:
            rows = []
            print(f"[gads-dg] marža {trg}: {e}")
        feed = G["feed_by_lang"].get(trg) or {}
        sl = G["feed_by_lang"].get("sl") or {}
        kinfo = ((_jload(NAST_FILE, {}) or {}).get("trgi", {}).get(trg, {}).get("kampanje", {}).get(kampanja) or {})   # kampanja = izvorna (vir)
        sem = asyncio.Semaphore(4)

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
                        kr, nas, opi = await asyncio.to_thread(ai_besedila, trg, post["naziv"], opis, kinfo.get("primeri"))
                    except Exception as e:
                        kr, nas, opi = "", [], []
                        post["napake"].append(f"AI besedila: {str(e)[:120]}")
                    ime = kr or (post["naziv"].split(",")[0][:25])
                    post.update({"kratko_ime": ime, "ad_group": f"{ime}, SKU: {sku}", "ad_name": ime, "naslovi": nas, "opisi": opi,
                                 "slike": await pripravi_slike(pid, sku, slike_url), "vkljuci": True, "status": "ok"})
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
        pid = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
        async with lock:
            d = pak_load()
            d["paketi"].insert(0, {"id": pid, "trg": trg, "kampanja": nova["ime"] if nova else kampanja, "vir_kampanja": kampanja,
                                   "nova_kampanja": nova, "status": "v_delu", "at": _lj_iso(),
                                   "postavke": [{"sku": s, "status": "caka"} for s in skus]})
            d["paketi"] = d["paketi"][:30]
            _jsave(PAK_FILE, d)
        asyncio.create_task(obdelaj(pid, trg, kampanja, skus))   # besedila v slogu izvorne kampanje
        return {"ok": True, "id": pid}

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
            x["opozorila"] = []
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
            if not any(s["vrsta"] in ("1x1", "191x1") for s in x.get("slike") or []):
                x["opozorila"].append("ni slike 1:1 ali 1,91:1 — dodaj jo v Editorju")
        return bn, kinfo

    @app.get("/gads-dg/api/paket/{pid}")
    async def dg_paket(request: Request, pid: str):
        if not prijava(request):
            return ni()
        p = next((x for x in pak_load()["paketi"] if x["id"] == pid), None)
        if not p:
            return {"ok": False, "error": "Paketa ni."}
        bn, kinfo = validiraj(p, _jload(NAST_FILE, {}) or {})
        return {"ok": True, "paket": p, "business_name": bn, "kampanja_najdena": bool(kinfo)}

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
                for s in x.get("slike") or []:
                    f = SLIKE_DIR / pid / x["sku"] / s["datoteka"]
                    if f.exists():
                        z.write(f, f"images/{x['sku']}/{s['datoteka']}")
                        mw.writerow([x["sku"], x["ad_group"], x.get("ad_name"), {"1x1": "Square 1:1", "191x1": "Landscape 1.91:1", "4x5": "Portrait 4:5"}[s["vrsta"]], f"images/{x['sku']}/{s['datoteka']}"])
            for x in p["postavke"]:
                rw.writerow([x["sku"], "izvoženo" if x in izb else ("izključeno" if x.get("status") == "ok" and not x.get("napake") else "napaka"),
                             "; ".join(x.get("napake") or []), "; ".join(x.get("opozorila") or [])])
            z.writestr("manifest.csv", "﻿" + man.getvalue())
            z.writestr("validation_report.csv", "﻿" + rep.getvalue())
            z.writestr("NAVODILA.txt", ("" 
                + ("0) NOVA KAMPANJA »" + nk["ime"] + "« (" + ST + ") — v pregledu uvoza mora biti Campaign: Added 1, nobena Updated.\n" if nk else "") +
                "1) Google Ads Editor: Get recent changes.\n"
                "2) Account > Import > From file > ads.csv  (pregled mora pokazati samo ADDED, nobenega UPDATED).\n"
                "3) Account > Import > Import image assets from files > mapa images (slike gredo v knjižnico).\n"
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
            if k is not None:
                for x in izb:
                    k.setdefault("ag_paket", {})[x["ad_group"].lower()] = pid
                    if x["ad_group"] not in k.setdefault("ad_groups", []):
                        k["ad_groups"].append(x["ad_group"])
                    if x["sku"] not in k.setdefault("skuji", []):
                        k["skuji"].append(x["sku"])
                tt["izbrana"] = p["kampanja"]
                _jsave(NAST_FILE, d)
        await pak_set(pid, lambda q: q.update(izvozeno=_lj_iso()))
        ime = f"suban_demandgen_{p['trg'].upper()}_{p['at'][:10]}.zip"
        zb.seek(0)
        return StreamingResponse(zb, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{ime}"'})

    print("[gads-dg] modul vklopljen")
