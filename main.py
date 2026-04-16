from fastapi import FastAPI, Query
from jobspy import scrape_jobs
import pandas as pd
import httpx
import asyncio
import uvicorn

app = FastAPI()

GREENHOUSE_COMPANIES = [
    "airbnb", "figma", "dropbox", "twitch", "coinbase",
    "robinhood", "plaid", "stripe", "brex", "rippling",
    "notion", "airtable", "lattice", "gusto", "checkr",
    "palantir", "databricks", "snowflake", "hubspot", "zendesk",
    "squarespace", "duolingo", "canva", "asana", "monday"
]

LEVER_COMPANIES = [
    "netflix", "reddit", "scale-ai", "openai", "anthropic",
    "cohere", "mistral", "perplexity", "together-ai", "anyscale",
    "weights-biases", "huggingface", "modal-labs", "replicate",
    "cursor", "codeium", "sourcegraph", "linear", "vercel", "supabase"
]

# Core role keywords to match against job titles
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

# Multiple Google search queries to get more results
GOOGLE_QUERIES = [
    "software engineer React AWS jobs USA",
    "full stack engineer TypeScript jobs USA",
    "frontend engineer React jobs United States",
    "backend engineer AWS jobs United States",
    "software developer TypeScript React jobs USA",
]

@app.get("/")
def root():
    return {"status": "JobSpy API is running"}

def matches_role(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in ROLE_KEYWORDS)

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
            if any(country in location_text.lower() for country in [
                "canada", "uk", "india", "germany", "france",
                "australia", "poland", "ireland", "israel"
            ]):
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
            if any(country in location_text.lower() for country in [
                "canada", "uk", "india", "germany", "france",
                "australia", "poland", "ireland", "israel"
            ]):
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

def scrape_google_jobs(query_str, hours_old):
    """Scrape Google Jobs with a single query string"""
    try:
        jobs = scrape_jobs(
            site_name=["google"],
            google_search_term=query_str,
            results_wanted=10,
            hours_old=hours_old,
            verbose=0
        )
        if jobs is not None and not jobs.empty:
            print(f"✅ Google [{query_str[:40]}]: {len(jobs)} jobs")
            return jobs
        else:
            print(f"⚠️ Google [{query_str[:40]}]: 0 jobs")
            return None
    except Exception as e:
        print(f"❌ Google [{query_str[:40]}]: {str(e)}")
        return None

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

    # --- Google Jobs (multiple queries to bypass 10-result limit) ---
    google_dfs = []
    for gq in GOOGLE_QUERIES:
        result = scrape_google_jobs(gq, hours_old)
        if result is not None:
            google_dfs.append(result)

    if google_dfs:
        combined_google = pd.concat(google_dfs, ignore_index=True)
        combined_google = combined_google.drop_duplicates(subset=["title", "company"], keep="first")
        for _, row in combined_google.iterrows():
            all_jobs.append({
                "company": str(row.get("company", "Unknown")),
                "role": str(row.get("title", "Unknown")),
                "location": str(row.get("location", "USA")),
                "link": str(row.get("job_url", "")),
                "description": str(row.get("description", ""))[:2000],
                "posted": str(row.get("date_posted", "N/A")),
                "source": "google"
            })
        print(f"✅ Google total: {len(combined_google)} unique jobs")

    # --- Greenhouse + Lever in parallel ---
    async with httpx.AsyncClient() as client:
        tasks = []
        tasks += [fetch_greenhouse_jobs(client, c) for c in GREENHOUSE_COMPANIES]
        tasks += [fetch_lever_jobs(client, c) for c in LEVER_COMPANIES]
        results_list = await asyncio.gather(*tasks)
        for job_list in results_list:
            all_jobs.extend(job_list)

    # Deduplicate all sources
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
