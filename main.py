from fastapi import FastAPI, Query
from jobspy import scrape_jobs
import pandas as pd
import httpx
import asyncio
import uvicorn

app = FastAPI()

# Confirmed working Greenhouse slugs
GREENHOUSE_COMPANIES = [
    "airbnb", "figma", "dropbox", "twitch", "coinbase",
    "robinhood", "stripe", "brex", "airtable", "lattice",
    "gusto", "checkr", "databricks", "hubspot",
    "squarespace", "duolingo", "asana", "lyft",
    "pinterest", "discord", "klaviyo", "datadog",
    "instacart", "amplitude", "mixpanel",
    # Fixed slugs
    "doordashusa",        # was "doordash"
    "plaid",              # try original again
    "rippling",           # try original again  
    "notion",             # try original again
    "snowflake",          # try original again
    "palantir",           # try original again
    "retool",             # try original again
    # New additions
    "uber", "lyft", "roblox", "snap",
    "mongodb", "confluent", "cloudflare",
    "gitlab", "hashicorp-inc", "grafana",
    "samsara", "anduril", "verkada",
    "gleanwork", "ramp"
]

# Confirmed working Lever slugs
LEVER_COMPANIES = [
    "mistral",  # only confirmed working one
    # Try fixed slugs
    "netflix",
    "openai",
    "scale-ai",
    "anyscale",
    "sourcegraph",
]

# Companies using Ashby ATS
ASHBY_COMPANIES = [
    "anthropic",
    "openai",
    "vercel",
    "linear",
    "supabase",
    "perplexity",
    "cohere",
    "replit",
    "cursor",
    "codeium",
    "modal",
    "replicate",
    "huggingface",
    "together",
    "weights-biases",
    "langchain",
    "pinecone",
    "weaviate",
    "qdrant",
    "chroma",
]

ROLE_KEYWORDS = [
    "software engineer", "software developer",
    "frontend engineer", "backend engineer",
    "full stack", "fullstack",
    "devops engineer", "sre", "site reliability",
    "machine learning engineer", "ml engineer",
    "ai engineer", "llm engineer",
    "cloud engineer", "platform engineer",
    "systems engineer", "react developer",
    "node engineer", "aws engineer"
]

@app.get("/")
def root():
    return {"status": "JobSpy API is running"}

def matches_role(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in ROLE_KEYWORDS)

def is_excluded_location(location_text: str) -> bool:
    excluded = [
        "canada", "uk", "india", "germany", "france",
        "australia", "poland", "ireland", "israel",
        "toronto", "ontario", "warsaw", "london",
        "berlin", "paris", "amsterdam", "dublin"
    ]
    loc_lower = location_text.lower()
    return any(c in loc_lower for c in excluded)

async def fetch_greenhouse_jobs(client, company):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
        r = await client.get(url, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Greenhouse {company}: status {r.status_code}")
            return []
        data = r.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            if not matches_role(title):
                continue
            location_text = ""
            if job.get("location"):
                location_text = job["location"].get("name", "")
            if is_excluded_location(location_text):
                continue
            jobs.append({
                "company": company.replace("-", " ").title(),
                "role": title,
                "location": location_text,
                "link": job.get("absolute_url", ""),
                "description": job.get("content", "")[:2000],
                "posted": "None",
                "source": "greenhouse"
            })
        if jobs:
            print(f"✅ Greenhouse {company}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"❌ Greenhouse {company}: {str(e)}")
        return []

async def fetch_lever_jobs(client, company):
    try:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        r = await client.get(url, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Lever {company}: status {r.status_code}")
            return []
        data = r.json()
        jobs = []
        for job in data:
            title = job.get("text", "")
            if not matches_role(title):
                continue
            location_text = job.get("categories", {}).get("location", "")
            if is_excluded_location(location_text):
                continue
            description = job.get("descriptionPlain", "")[:2000]
            jobs.append({
                "company": company.replace("-", " ").title(),
                "role": title,
                "location": location_text,
                "link": job.get("hostedUrl", ""),
                "description": description,
                "posted": "None",
                "source": "lever"
            })
        if jobs:
            print(f"✅ Lever {company}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"❌ Lever {company}: {str(e)}")
        return []

async def fetch_ashby_jobs(client, company):
    """Ashby ATS - used by Anthropic, OpenAI, Vercel, Linear etc."""
    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        r = await client.get(url, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Ashby {company}: status {r.status_code}")
            return []
        data = r.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            if not matches_role(title):
                continue
            location_text = job.get("location", "") or ""
            if is_excluded_location(location_text):
                continue
            description = job.get("descriptionHtml", "") or job.get("description", "")
            jobs.append({
                "company": company.replace("-", " ").title(),
                "role": title,
                "location": location_text,
                "link": job.get("jobUrl", ""),
                "description": description[:2000],
                "posted": job.get("publishedAt", "None"),
                "source": "ashby"
            })
        if jobs:
            print(f"✅ Ashby {company}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"❌ Ashby {company}: {str(e)}")
        return []

@app.get("/jobs")
async def get_jobs(
    query: str = Query(default="software engineer AWS"),
    location: str = Query(default="United States"),
    hours_old: int = Query(default=24),
    results: int = Query(default=50)
):
    all_jobs = []

    # --- Indeed (most reliable) ---
    try:
        jobs = scrape_jobs(
            site_name=["indeed"],
            search_term=query,
            location=location,
            results_wanted=25,
            hours_old=hours_old,
            country_indeed="USA",
            verbose=1
        )
        if jobs is not None and not jobs.empty:
            for _, row in jobs.iterrows():
                all_jobs.append({
                    "company": str(row.get("company", "Unknown")),
                    "role": str(row.get("title", "Unknown")),
                    "location": str(row.get("location", "USA")),
                    "link": str(row.get("job_url", "")),
                    "description": str(row.get("description", ""))[:2000],
                    "posted": str(row.get("date_posted", "N/A")),
                    "source": "indeed"
                })
            print(f"✅ Indeed: {len(jobs)} jobs found")
        else:
            print(f"⚠️ Indeed: 0 jobs found")
    except Exception as e:
        print(f"❌ Indeed failed: {str(e)}")

    # --- Greenhouse + Lever + Ashby in parallel ---
    async with httpx.AsyncClient() as client:
        tasks = []
        tasks += [fetch_greenhouse_jobs(client, c) for c in GREENHOUSE_COMPANIES]
        tasks += [fetch_lever_jobs(client, c) for c in LEVER_COMPANIES]
        tasks += [fetch_ashby_jobs(client, c) for c in ASHBY_COMPANIES]
        results_list = await asyncio.gather(*tasks)
        for job_list in results_list:
            all_jobs.extend(job_list)

    # Deduplicate
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        key = job.get("link") or (job["role"] + job["company"]).lower().replace(" ", "")
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    print(f"✅ Total unique jobs: {len(unique_jobs)}")
    return {"jobs": unique_jobs, "total": len(unique_jobs)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
