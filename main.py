import httpx
import asyncio
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HiringRoom Scraper API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9",
}

LABORATORIOS = [
    ("Laboratorios Elea",  "https://elea.hiringroom.com/jobs"),
    ("Lab. Richmond",      "https://labrichmond.hiringroom.com/jobs"),
    ("Baliarda",           "https://baliarda.hiringroom.com/jobs"),
    ("Laboratorio Lazar",  "https://laboratoriolazar.hiringroom.com/jobs"),
    ("Laboratorio Rapela", "https://labrapela.hiringroom.com/jobs"),
    ("Droguería del Sud",  "https://delsud.hiringroom.com/jobs"),
    ("Laboratorio ENA",    "https://laboratorioena.hiringroom.com/jobs"),
    ("Scienza Argentina",  "https://scienza.hiringroom.com/jobs"),
    ("Adium Argentina",    "https://adium.hiringroom.com/jobs"),
    ("Montpellier",        "https://montpellier.hiringroom.com/jobs"),
]

class Job(BaseModel):
    empresa: str
    title: str
    location: str
    area: str
    tags: str
    posted: str
    url: str

class SearchResult(BaseModel):
    total: int
    empresas: int
    jobs: list[Job]

def clean_tags(tags_str: str) -> str:
    tags = [t.strip() for t in tags_str.split(",")]
    seen, unique = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return ", ".join(unique)

def clean_posted(posted_str: str) -> str:
    return posted_str.replace("Nuevo", "").strip()

async def scrape_lab(client, nombre: str, base_url: str, keyword: str = "") -> list[Job]:
    jobs = []
    subdomain = base_url.split("//")[1].split(".")[0]
    try:
        r = await client.get(base_url)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.card.hoverable")
        for card in cards:
            title_el = card.select_one("h4.name__vacancy")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
            if keyword and keyword.lower() not in title.lower():
                continue
            spans = card.select("p.card-text span.font-weight-light")
            location = spans[0].get_text(strip=True) if len(spans) > 0 else ""
            area     = spans[1].get_text(strip=True) if len(spans) > 1 else ""
            tags_raw = ", ".join(t.get_text(strip=True) for t in card.select("span.tag-vacancy"))
            date_el  = card.select_one("p.vacancy-time")
            posted   = date_el.get_text(strip=True) if date_el else ""
            link     = card.find_parent("a")
            if link:
                href = link.get("href", "")
                url = f"https://{subdomain}.hiringroom.com{href}" if href.startswith("/") else href
            else:
                url = base_url
            jobs.append(Job(
                empresa=nombre,
                title=title,
                location=location,
                area=area,
                tags=clean_tags(tags_raw),
                posted=clean_posted(posted),
                url=url,
            ))
    except Exception as e:
        logger.warning(f"Error scrapeando {nombre}: {e}")
    return jobs

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>HiringRoom Scraper API v1</h1><p><a href='/docs'>Docs</a> · <a href='/health'>Health</a> · <a href='/jobs'>Todos los avisos</a></p>"

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/empresas")
async def get_empresas():
    return [{"nombre": n, "url": u} for n, u in LABORATORIOS]

@app.get("/jobs", response_model=SearchResult)
async def get_jobs(
    q: str = Query(default="", description="Filtrar por título (opcional)"),
    empresa: str = Query(default="", description="Filtrar por empresa (opcional)"),
):
    labs = LABORATORIOS
    if empresa:
        labs = [(n, u) for n, u in LABORATORIOS if empresa.lower() in n.lower()]

    all_jobs = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        tasks = [scrape_lab(client, n, u, keyword=q) for n, u in labs]
        results = await asyncio.gather(*tasks)
        for r in results:
            all_jobs.extend(r)

    empresas_con_resultados = len(set(j.empresa for j in all_jobs))
    return SearchResult(total=len(all_jobs), empresas=empresas_con_resultados, jobs=all_jobs)

