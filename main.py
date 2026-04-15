import os
import json
import re
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


class AdRequest(BaseModel):
    input: str
    mode: str
    pt_count: int = 1
    hl_count: int = 1


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.post("/generate")
def generate(req: AdRequest):
    if req.mode == "url":
        user_msg = f"Preberi to stran in ustvari Meta oglase: {req.input}"
    else:
        user_msg = f"Na podlagi tega opisa ustvari Meta oglase:\n\n{req.input}"

    # Build explicit PT and HL placeholders so model knows exact count
    pt_placeholders = ", ".join([f'"PT tekst {i+1}"' for i in range(req.pt_count)])
    hl_placeholders = ", ".join([f'"HL tekst {i+1}"' for i in range(req.hl_count)])

    prompt = f"""{user_msg}

OBVEZNO ustvari TOČNO {req.pt_count} Primary Text(ov) IN TOČNO {req.hl_count} Headline(ov) za VSAK jezik.

Pravila za Primary Text (ponovi {req.pt_count}x za vsak jezik):
- 2-3 kratke vrstice
- Vsaj 2-3 emoji-jev razporejenih po besedilu
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
        return data
    except json.JSONDecodeError as e:
        return {"error": f"JSON napaka: {str(e)}"}
