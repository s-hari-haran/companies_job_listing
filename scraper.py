import pandas as pd
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import time
import random
from urllib.parse import urljoin, urlparse
import re

# ================= CONFIGURATION =================
INPUT_FILE = "companies.xlsx"
OUTPUT_FILE = "submission_result.xlsx"
TARGET_TOTAL_JOBS = 200

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ================= PART 1: SEARCH & ENRICHMENT =================

def find_careers_on_website(website_url):
    """Try to find careers page by scraping the company website"""
    if not website_url:
        return None
    
    try:
        resp = requests.get(website_url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Look for careers/jobs links in the page
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                text = link.text.lower()
                
                if any(keyword in href or keyword in text for keyword in ['career', 'job', 'work-with-us', 'join-us', 'join-our-team', 'hiring', 'openings']):
                    careers_url = urljoin(website_url, link['href'])
                    # Check if it's a valid URL (not anchor or mailto)
                    if careers_url.startswith('http') and '#' not in careers_url and 'mailto:' not in careers_url:
                        return careers_url
    except:
        pass
    
    return None

def google_dork_search(company_name):
    """
    Uses DuckDuckGo to find the Official Site, LinkedIn, and Careers Page.
    Returns a dictionary of URLs.
    """
    data = {"website": None, "linkedin": None, "careers_url": None, "job_listings_url": None}
    
    try:
        ddgs = DDGS()
        
        # 1. Find Website - try multiple queries
        queries = [
            f'"{company_name}" official website',
            f'{company_name} company site',
            company_name
        ]
        
        for query in queries:
            if data['website']:
                break
            try:
                results = ddgs.text(query, max_results=5)
                for r in results:
                    link = r.get('href', r.get('body', ''))
                    if not link:
                        continue
                    
                    # Extract URL if it's in body
                    if 'http' in link and not link.startswith('http'):
                        url_match = re.search(r'https?://[^\s]+', link)
                        if url_match:
                            link = url_match.group(0)
                    
                    if "linkedin.com/company" in link and not data['linkedin']:
                        data['linkedin'] = link
                    elif "linkedin.com" not in link and not data['website']:
                        # Filter out aggregator sites
                        if not any(x in link.lower() for x in ['glassdoor', 'crunchbase', 'bloomberg', 'wikipedia', 'indeed', 'facebook', 'twitter', 'reddit', 'quora', 'youtube']):
                            data['website'] = link
                            break
                time.sleep(0.5)
            except:
                continue
        
        # 2. Search for LinkedIn if not found
        if not data['linkedin']:
            try:
                query_li = f'{company_name} site:linkedin.com/company'
                li_results = ddgs.text(query_li, max_results=3)
                for r in li_results:
                    link = r.get('href', r.get('body', ''))
                    if "linkedin.com/company" in link:
                        # Extract clean LinkedIn URL
                        match = re.search(r'(https?://[\w.]*linkedin\.com/company/[^\s/?#]+)', link)
                        if match:
                            data['linkedin'] = match.group(1)
                        else:
                            data['linkedin'] = link
                        break
            except:
                pass
        
        time.sleep(random.uniform(1, 2))  # Rate limiting
        
        # 3. Try to find careers page on the website directly
        if data['website'] and not data['careers_url']:
            careers_from_site = find_careers_on_website(data['website'])
            if careers_from_site:
                data['careers_url'] = careers_from_site
                # Check if it's an ATS platform
                if any(ats in careers_from_site.lower() for ats in ['lever.co', 'greenhouse.io', 'zohorecruit', 'workable', 'ashbyhq', 'teamtailor', 'personio', 'jobs.', 'careers.']):
                    data['job_listings_url'] = careers_from_site
        
        # 4. Search for ATS-specific job pages
        if not data['job_listings_url']:
            try:
                # Try individual ATS searches
                ats_platforms = ['lever.co', 'greenhouse.io', 'teamtailor.com', 'personio.com', 'zohorecruit.com']
                for ats in ats_platforms:
                    query_ats = f'{company_name} site:{ats}'
                    ats_results = ddgs.text(query_ats, max_results=1)
                    for r in ats_results:
                        link = r.get('href', r.get('body', ''))
                        if ats in link:
                            data['job_listings_url'] = link
                            data['careers_url'] = link
                            break
                    if data['job_listings_url']:
                        break
                    time.sleep(0.5)
            except:
                pass
        
        time.sleep(random.uniform(1, 2))
        
        # 5. Fallback: Generic careers page search
        if not data['careers_url']:
            try:
                query_careers = f'{company_name} careers'
                career_results = ddgs.text(query_careers, max_results=5)
                for r in career_results:
                    link = r.get('href', r.get('body', ''))
                    if not link:
                        continue
                    
                    # Extract URL from body if needed
                    if 'http' in link and not link.startswith('http'):
                        url_match = re.search(r'https?://[^\s]+', link)
                        if url_match:
                            link = url_match.group(0)
                    
                    if any(x in link.lower() for x in ['career', 'job', 'work-with', 'join', 'hiring', 'opening']):
                        # Avoid LinkedIn and other aggregators
                        if not any(x in link.lower() for x in ['linkedin', 'glassdoor', 'indeed', 'facebook']):
                            data['careers_url'] = link
                            if not data['job_listings_url']:
                                data['job_listings_url'] = link
                            break
            except:
                pass

    except Exception as e:
        print(f"  Search error for {company_name}: {e}")
        time.sleep(3)

    return data

# ================= PART 2: ATS RECOGNITION & SCRAPING =================

def scrape_lever(soup, base_url):
    """Scrapes Lever.co pages"""
    jobs = []
    
    # Lever structure: div.posting or a.posting-title
    postings = soup.find_all("div", class_="posting")
    
    if not postings:
        # Alternative: Look for posting links
        posting_links = soup.find_all("a", class_="posting-title")
        for link in posting_links[:3]:
            try:
                title = link.text.strip()
                url = link.get('href', '')
                if not url.startswith('http'):
                    url = urljoin(base_url, url)
                
                # Find location nearby
                parent = link.find_parent("div", class_="posting")
                location = "Remote/Not specified"
                if parent:
                    loc_tag = parent.find("span", class_="sort-by-location")
                    if not loc_tag:
                        loc_tag = parent.find("span", class_="location")
                    if loc_tag:
                        location = loc_tag.text.strip()
                
                jobs.append({
                    "title": title,
                    "url": url,
                    "location": location,
                    "source": "Lever"
                })
            except Exception as e:
                continue
    else:
        for post in postings[:3]:
            try:
                title_tag = post.find("h5")
                if not title_tag:
                    title_tag = post.find("a", class_="posting-title")
                
                title = title_tag.text.strip() if title_tag else "Unknown Position"
                
                link_tag = post.find("a", class_="posting-title")
                if not link_tag:
                    link_tag = post.find("a", href=True)
                
                url = link_tag.get('href', '') if link_tag else ''
                if url and not url.startswith('http'):
                    url = urljoin(base_url, url)
                
                loc_tag = post.find("span", class_="sort-by-location")
                if not loc_tag:
                    loc_tag = post.find("span", class_="location")
                location = loc_tag.text.strip() if loc_tag else "Remote/Not specified"
                
                if url:
                    jobs.append({
                        "title": title,
                        "url": url,
                        "location": location,
                        "source": "Lever"
                    })
            except Exception as e:
                continue
    
    return jobs

def scrape_greenhouse(soup, base_url):
    """Scrapes Greenhouse.io pages"""
    jobs = []
    
    # Greenhouse structure: div.opening or section.level--0
    openings = soup.find_all("div", class_="opening")
    
    if not openings:
        # Try alternative structure
        openings = soup.find_all("section", class_=lambda x: x and "level" in x)
    
    for opening in openings[:3]:
        try:
            link_tag = opening.find("a", href=True)
            if not link_tag:
                continue
            
            title = link_tag.text.strip()
            url = link_tag.get('href', '')
            
            # Greenhouse URLs are usually absolute
            if url and not url.startswith('http'):
                # Could be relative to boards.greenhouse.io or absolute path
                if url.startswith('/'):
                    parsed = urlparse(base_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"
                else:
                    url = urljoin(base_url, url)
            
            # Find location
            location = "Not specified"
            loc_tag = opening.find("span", class_="location")
            if not loc_tag:
                loc_tag = opening.find("div", class_="location")
            if loc_tag:
                location = loc_tag.text.strip()
            
            jobs.append({
                "title": title,
                "url": url,
                "location": location,
                "source": "Greenhouse"
            })
        except Exception as e:
            continue
    
    return jobs

def scrape_personio(soup, base_url):
    """Scrapes Personio job boards"""
    jobs = []
    
    # Personio typically uses data-test attributes
    job_items = soup.find_all("a", attrs={"data-test": "job-item"})
    
    if not job_items:
        # Fallback: Look for links with /job/ in href
        all_links = soup.find_all("a", href=True)
        job_items = [a for a in all_links if '/job/' in a.get('href', '')]
    
    for item in job_items[:3]:
        try:
            title = item.text.strip()
            url = item.get('href', '')
            if url and not url.startswith('http'):
                url = urljoin(base_url, url)
            
            # Location might be nearby
            location = "See job posting"
            
            jobs.append({
                "title": title,
                "url": url,
                "location": location,
                "source": "Personio"
            })
        except:
            continue
    
    return jobs

def scrape_teamtailor(soup, base_url):
    """Scrapes Teamtailor job boards"""
    jobs = []
    
    # Teamtailor uses li elements with job data
    job_items = soup.find_all("li", class_=lambda x: x and "jobs" in str(x).lower())
    
    if not job_items:
        job_items = soup.find_all("a", href=lambda x: x and "/jobs/" in x)
    
    for item in job_items[:3]:
        try:
            if item.name == "a":
                link_tag = item
            else:
                link_tag = item.find("a", href=True)
            
            if not link_tag:
                continue
            
            title = link_tag.text.strip()
            url = link_tag.get('href', '')
            if url and not url.startswith('http'):
                url = urljoin(base_url, url)
            
            location = "Not specified"
            loc_tag = item.find("span", class_="location")
            if loc_tag:
                location = loc_tag.text.strip()
            
            jobs.append({
                "title": title,
                "url": url,
                "location": location,
                "source": "Teamtailor"
            })
        except:
            continue
    
    return jobs

def scrape_generic_careers(soup, base_url):
    """
    Fallback: Looks for <a> tags containing job-related keywords
    """
    jobs = []
    links = soup.find_all("a", href=True)
    
    seen_urls = set()
    
    for a in links:
        href = a.get('href', '')
        text = a.text.strip().lower()
        
        # Filter logic - look for job-related URLs
        if any(keyword in href.lower() for keyword in ['/job/', '/jobs/', '/career', '/position', '/opening', '/vacancy']):
            full_url = urljoin(base_url, href)
            
            # Avoid duplicates and non-job pages
            if full_url not in seen_urls and not any(x in full_url.lower() for x in ['#', 'javascript:', 'mailto:']):
                seen_urls.add(full_url)
                
                title = a.text.strip() or "Job Opening"
                
                # Try to find location nearby
                location = "See job posting"
                parent = a.find_parent()
                if parent:
                    loc_indicators = parent.find_all(string=lambda x: x and any(loc in str(x).lower() for loc in ['remote', 'location:', 'office']))
                    if loc_indicators:
                        location = str(loc_indicators[0]).strip()[:50]
                
                jobs.append({
                    "title": title,
                    "url": full_url,
                    "location": location,
                    "source": "Generic"
                })
        
        if len(jobs) >= 3:
            break
    
    return jobs

def get_job_description(url):
    """
    Visits the specific job page to get the description text.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            # Check if response is HTML
            content_type = resp.headers.get('Content-Type', '').lower()
            if 'pdf' in content_type or resp.content[:4] == b'%PDF':
                return "Job description is in PDF format"
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # Try to find job description container
            desc_container = soup.find("div", class_=lambda x: x and any(k in str(x).lower() for k in ["description", "content", "job-detail"]))
            
            if desc_container:
                text = desc_container.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)
            
            # Clean and return first 400 chars
            text = ' '.join(text.split())  # Remove extra whitespace
            # Remove any non-printable characters
            text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t')
            return text[:400] + "..." if len(text) > 400 else text
    except Exception as e:
        return f"Description unavailable"
    
    return "No description found"

# ================= PART 3: MAIN EXECUTION =================

def main():
    print(f"📂 Reading {INPUT_FILE}...")
    try:
        df = pd.read_excel(INPUT_FILE)
    except Exception as e:
        print(f"❌ Error reading input file: {e}")
        return

    print(f"✅ Loaded {len(df)} companies\n")

    # Ensure all required columns exist - match EXACT names from the Excel
    required_cols = [
        'Website URL', 'Linkedin URL', 'Careers Page URL', 'Job listings page URL',
        'job post1 URL', 'job post1 title', 'job post1 location', 'job post1 description',
        'job post2 URL', 'job post2 title', 'job post2 location', 'job post2 description',
        'job post3 URL', 'job post3 title', 'job post3 location', 'job post3 description'
    ]
    
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    total_jobs_found = 0
    companies_processed = 0
    
    print("🚀 Starting Web Scraping (No AI, pure web scraping)...\n")
    print("=" * 80)

    for index, row in df.iterrows():
        # Skip already processed companies (start from index 60)
        if index < 60:
            continue
        if total_jobs_found >= TARGET_TOTAL_JOBS:
            print(f"\n🎉 TARGET REACHED! Found {total_jobs_found} jobs across {companies_processed} companies!")
            break

        company = str(row['Company Name']).strip()
        if not company or company == 'nan':
            continue

        print(f"\n[{index+1}/{len(df)}] 🏢 {company}")
        companies_processed += 1

        # Skip if already has data
        if pd.notna(row.get('job post1 URL')):
            print("   ⏭️  Already has job data, skipping...")
            # Count existing jobs
            for i in range(1, 4):
                if pd.notna(row.get(f'job post{i} URL')):
                    total_jobs_found += 1
            continue

        # --- STEP 1: ENRICHMENT (Search) ---
        print("   🔍 Searching for company URLs...")
        search_data = google_dork_search(company)
        
        # Save enrichment data
        if search_data['website']:
            df.at[index, 'Website URL'] = search_data['website']
            print(f"   ✓ Website: {search_data['website'][:60]}")
        
        if search_data['linkedin']:
            df.at[index, 'Linkedin URL'] = search_data['linkedin']
            print(f"   ✓ LinkedIn: {search_data['linkedin'][:60]}")
        
        if search_data['careers_url']:
            df.at[index, 'Careers Page URL'] = search_data['careers_url']
            print(f"   ✓ Careers: {search_data['careers_url'][:60]}")
        
        job_board_url = search_data['job_listings_url'] or search_data['careers_url']
        if job_board_url:
            df.at[index, 'Job listings page URL'] = job_board_url

        # --- STEP 2: SCRAPING JOBS ---
        if not job_board_url:
            print("   ⚠️  No careers/jobs page found")
            time.sleep(random.uniform(1, 2))
            continue

        print(f"   🕷️  Scraping jobs from: {job_board_url[:60]}...")
        
        try:
            resp = requests.get(job_board_url, headers=HEADERS, timeout=12)
            
            if resp.status_code != 200:
                print(f"   ❌ HTTP {resp.status_code}")
                time.sleep(random.uniform(2, 3))
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            found_jobs = []
            
            # Detect ATS and use specific scraper
            url_lower = job_board_url.lower()
            
            if "lever.co" in url_lower:
                print("   🎯 Detected: Lever")
                found_jobs = scrape_lever(soup, job_board_url)
            elif "greenhouse.io" in url_lower or "greenhouse.com" in url_lower:
                print("   🎯 Detected: Greenhouse")
                found_jobs = scrape_greenhouse(soup, job_board_url)
            elif "zohorecruit.com" in url_lower or "zoho" in url_lower:
                print("   🎯 Detected: Zoho Recruit")
                found_jobs = scrape_generic_careers(soup, job_board_url)
            elif "personio" in url_lower:
                print("   🎯 Detected: Personio")
                found_jobs = scrape_personio(soup, job_board_url)
            elif "teamtailor" in url_lower:
                print("   🎯 Detected: Teamtailor")
                found_jobs = scrape_teamtailor(soup, job_board_url)
            elif "workable.com" in url_lower:
                print("   🎯 Detected: Workable")
                found_jobs = scrape_generic_careers(soup, job_board_url)
            elif "ashbyhq.com" in url_lower:
                print("   🎯 Detected: Ashby")
                found_jobs = scrape_generic_careers(soup, job_board_url)
            else:
                print("   🎯 Using: Generic scraper")
                found_jobs = scrape_generic_careers(soup, job_board_url)

            # --- STEP 3: FILL EXCEL & GET DESCRIPTIONS ---
            if not found_jobs:
                print("   ⚠️  No jobs found on page")
            
            for i, job in enumerate(found_jobs):
                if i >= 3:
                    break
                
                job_num = i + 1
                
                # Save job data
                df.at[index, f'job post{job_num} title'] = job['title']
                df.at[index, f'job post{job_num} URL'] = job['url']
                df.at[index, f'job post{job_num} location'] = job['location']
                
                print(f"      ✅ Job {job_num}: {job['title'][:50]}")
                
                # Get description (with delay)
                time.sleep(random.uniform(1, 2))
                desc = get_job_description(job['url'])
                df.at[index, f'job post{job_num} description'] = desc
                
                total_jobs_found += 1
                
                if total_jobs_found >= TARGET_TOTAL_JOBS:
                    break

        except Exception as e:
            print(f"   ❌ Scraping error: {e}")
        
        # Save progress every 5 companies
        if index % 5 == 0:
            df.to_excel(OUTPUT_FILE, index=False)
            print(f"\n💾 Progress saved ({total_jobs_found} jobs so far)")
        
        # Respectful delay between companies
        time.sleep(random.uniform(3, 6))

    # Final save
    df.to_excel(OUTPUT_FILE, index=False)
    print("\n" + "=" * 80)
    print(f"✅ COMPLETE!")
    print(f"📊 Total jobs found: {total_jobs_found}")
    print(f"🏢 Companies processed: {companies_processed}")
    print(f"💾 Saved to: {OUTPUT_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    main()
