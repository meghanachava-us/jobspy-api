from fastapi import FastAPI, Query
from jobspy import scrape_jobs
import pandas as pd
import httpx
import asyncio
from xml.etree import ElementTree as ET
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

@app.get("/")
def root():
    return {"status": "JobSpy API is running"}

async def fetch_greenhouse_jobs(client, company, keywords):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
        r = await client.get(url, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            if not any(k.lower() in title.lower() for k in keywords):
                continue
            location_text = ""
            if job.get("location"):
                location_text = job["location"].get("name", "")
            jobs.append({
                "company": company.replace("-", " ").title(),
                "role": title,
                "location": location_text,
                "link": job.get("absolute_url", ""),
                "description": job.get("content", "")[:2000],
                "posted": "None",
                "source": "greenhouse"
            })
        return jobs
    except Exception as e:
        print(f"❌ Greenhouse {company}: {str(e)}")
        return []

async def fetch_lever_jobs(client, company, keywords):
    try:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        r = await client.get(url, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for job in data:
            title = job.get("text", "")
            if not any(k.lower() in title.lower() for k in keywords):
                continue
            location_text = job.get("categories", {}).get("location", "")
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
        return jobs
    except Exception as e:
        print(f"❌ Lever {company}: {str(e)}")
        return []

@app.get("/jobs")
async def get_jobs(
    query: str = Query(default="software engineer AWS"),
    location: str = Query(default="United States"),
    hours_old: int = Query(default=24),
    results: int = Query(default=50)
):
    keywords = query.split()
    all_jobs = []

    # --- JobSpy: Indeed, ZipRecruiter, Glassdoor, Google Jobs ---
    # Google Jobs indexes LinkedIn + 100s of other job boards
    jobspy_sites = ["indeed", "zip_recruiter", "glassdoor", "google"]
    
    for site in jobspy_sites:
        try:
            kwargs = dict(
                site_name=[site],
                search_term=query,
                location=location,
                results_wanted=results // len(jobspy_sites),
                hours_old=hours_old,
                country_indeed="USA",
                verbose=1
            )
            # Google Jobs needs a specific search term format
            if site == "google":
                kwargs["google_search_term"] = f"{query} jobs in United States"
                kwargs.pop("location", None)

            jobs = scrape_jobs(**kwargs)

            if jobs is not None and not jobs.empty:
                for _, row in jobs.iterrows():
                    all_jobs.append({
                        "company": str(row.get("company", "Unknown")),
                        "role": str(row.get("title", "Unknown")),
                        "location": str(row.get("location", "USA")),
                        "link": str(row.get("job_url", "")),
                        "description": str(row.get("description", ""))[:2000],
                        "posted": str(row.get("date_posted", "N/A")),
                        "source": str(row.get("site", site))
                    })
                print(f"✅ {site}: {len(jobs)} jobs found")
            else:
                print(f"⚠️ {site}: 0 jobs found")

        except Exception as e:
            print(f"❌ {site} failed: {str(e)}")
            continue

    # --- Greenhouse + Lever in parallel ---
    async with httpx.AsyncClient() as client:
        tasks = []
        tasks += [fetch_greenhouse_jobs(client, c, keywords) for c in GREENHOUSE_COMPANIES]
        tasks += [fetch_lever_jobs(client, c, keywords) for c in LEVER_COMPANIES]

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
