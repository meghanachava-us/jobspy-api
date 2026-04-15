from fastapi import FastAPI, Query
from jobspy import scrape_jobs
import pandas as pd
import uvicorn

app = FastAPI()

@app.get("/")
def root():
    return {"status": "JobSpy API is running"}

@app.get("/jobs")
def get_jobs(
    query: str = Query(default="software engineer AWS"),
    location: str = Query(default="United States"),
    hours_old: int = Query(default=24),
    results: int = Query(default=50)
):
    try:
        jobs = scrape_jobs(
            site_name=["linkedin", "indeed", "zip_recruiter", "glassdoor"],
            search_term=query,
            location=location,
            results_wanted=results,
            hours_old=hours_old,
            country_indeed="USA",
            linkedin_fetch_description=True
        )

        if jobs is None or jobs.empty:
            return {"jobs": [], "total": 0}

        result = []
        for _, row in jobs.iterrows():
            result.append({
                "company":     str(row.get("company", "Unknown")),
                "role":        str(row.get("title", "Unknown")),
                "location":    str(row.get("location", "USA")),
                "link":        str(row.get("job_url", "")),
                "description": str(row.get("description", ""))[:2000],
                "posted":      str(row.get("date_posted", "N/A")),
                "source":      str(row.get("site", "Unknown"))
            })

        return {"jobs": result, "total": len(result)}

    except Exception as e:
        return {"error": str(e), "jobs": [], "total": 0}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
