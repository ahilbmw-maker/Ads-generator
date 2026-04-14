import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

class AdRequest(BaseModel):
    input: str
    mode: str  # "url" ali "text"
    pt_count: int = 1
    hl_count: int = 1

@app.get("/")
def root():
    from fastapi.responses import FileResponse
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

Jeziki: SL (izvirnik), HR (latinica), RS (latinica, brez cirilice), HU, CZ, SK, PL, GR (grška pisava), RO (latinica), BG (cirilica).

Vrni SAMO veljaven JSON brez markdown:
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

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        tools=[{{"type": "web_search_20250305", "name": "web_search"}}] if req.mode == "url" else [],
        messages=[{{"role": "user", "content": prompt}}]
    )
    
    import json, re
    text = "".join(b.text for b in message.content if hasattr(b, "text"))
    match = re.search(r'\{{[\s\S]*\}}', text)
    return json.loads(match.group()) if match else {{"error": "Napaka pri generiranju"}}
