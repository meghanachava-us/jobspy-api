@app.get("/jobs")
def get_jobs(
    query: str = Query(default="software engineer AWS"),
    location: str = Query(default="United States"),
    hours_old: int = Query(default=24),
    results: int = Query(default=50)
):
    all_jobs = []

    # Scrape each site separately so one failure doesn't kill others
    sites = ["indeed", "linkedin", "zip_recruiter", "glassdoor"]
    
    for site in sites:
        try:
            jobs = scrape_jobs(
                site_name=[site],
                search_term=query,
                location=location,
                results_wanted=results // len(sites),  # split evenly
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=True,
                verbose=1
            )
            if jobs is not None and not jobs.empty:
                all_jobs.append(jobs)
                print(f"✅ {site}: {len(jobs)} jobs found")
            else:
                print(f"⚠️ {site}: 0 jobs found")
        except Exception as e:
            print(f"❌ {site} failed: {str(e)}")
            continue  # skip failed site, continue with others

    if not all_jobs:
        return {"jobs": [], "total": 0}

    # Combine all results
    import pandas as pd
    combined = pd.concat(all_jobs, ignore_index=True)
    
    # Deduplicate by title + company
    combined = combined.drop_duplicates(
        subset=["title", "company"], 
        keep="first"
    )

    result = []
    for _, row in combined.iterrows():
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
