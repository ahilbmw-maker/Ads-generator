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

    prompt = f"""{user_msg}

Ustvari:
- {req.pt_count}x Primary Text (kratek, z emoji, brez cen, prodajno usmerjen)
- {req.hl_count}x Headline (kratek, 1 emoji, brez cen)

Jeziki: SL (izvirnik), HR (latinica), RS (SAMO latinica, nikoli cirilica), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (SAMO cirilica).

Vrni SAMO veljaven JSON brez markdown oznak, brez ```json, samo golo JSON besedilo:
{{
  "product": "ime izdelka",
  "sl": {{"pt": ["..."], "hl": ["..."]}},
  "hr": {{"pt": ["..."], "hl": ["..."]}},
  "rs": {{"pt": ["..."], "hl": ["..."]}},
  "hu": {{"pt": ["..."], "hl": ["..."]}},
  "cz": {{"pt": ["..."], "hl": ["..."]}},
  "sk": {{"pt": ["..."], "hl": ["..."]}},
  "pl": {{"pt": ["..."], "hl": ["..."]}},
  "gr": {{"pt": ["..."], "hl": ["..."]}},
  "ro": {{"pt": ["..."], "hl": ["..."]}},
  "bg": {{"pt": ["..."], "hl": ["..."]}}
}}"""

    tools = [{"type": "web_search_20250305", "name": "web_search"}] if req.mode == "url" else []

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4000,
        tools=tools if tools else anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}]
    )

    # Zberemo vse text bloke iz odgovora (tudi po tool_use)
    text = ""
    for block in message.content:
        if hasattr(block, "text"):
            text += block.text

    # Poiščemo JSON — tudi če je zavit v ```
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Vzamemo prvi { ... } blok
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return {"error": "Claude ni vrnil veljavnega JSON. Poskusi znova."}

    try:
        data = json.loads(match.group())
        return data
    except json.JSONDecodeError as e:
        return {"error": f"JSON napaka: {str(e)}"}
