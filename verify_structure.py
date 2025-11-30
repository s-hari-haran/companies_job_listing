"""
Quick verification script to check if the scraper matches the Excel structure
"""
import pandas as pd

print("🔍 Verifying Excel Structure vs Code...\n")

# Load Excel
df = pd.read_excel("companies.xlsx")

print("📊 Current Excel Columns:")
for i, col in enumerate(df.columns, 1):
    print(f"   {i}. '{col}'")

print(f"\n📏 Shape: {df.shape[0]} rows × {df.shape[1]} columns")

# Check what the code expects
code_expects = [
    'Website URL', 'Linkedin URL', 'Careers Page URL', 'Job listings page URL',
    'job post1 URL', 'job post1 title', 'job post1 location', 'job post1 description',
    'job post2 URL', 'job post2 title', 'job post2 location', 'job post2 description',
    'job post3 URL', 'job post3 title', 'job post3 location', 'job post3 description'
]

print("\n✅ Code expects these columns:")
for col in code_expects:
    exists = col in df.columns
    icon = "✓" if exists else "✗ (will be created)"
    print(f"   {icon} '{col}'")

# Check for sample data
print("\n📝 Sample Data Check:")
sample_companies = df[df['job post1 URL'].notna()].head(2)
print(f"   Found {len(sample_companies)} companies with existing job data")

if len(sample_companies) > 0:
    for idx, row in sample_companies.iterrows():
        print(f"\n   Company: {row['Company Name']}")
        print(f"   Job 1 Title: {row['job post1 title']}")
        print(f"   Job 1 URL: {row['job post1 URL'][:60]}...")

empty_companies = df[df['job post1 URL'].isna()]
print(f"\n   📊 {len(empty_companies)} companies need scraping")

print("\n" + "="*60)
print("✅ VERIFICATION COMPLETE")
print("="*60)
print("\n💡 The improved scraper will:")
print("   1. Skip companies that already have job data")
print("   2. Search for missing Website/LinkedIn/Careers URLs")
print("   3. Scrape jobs from the Job Listings page")
print("   4. Add location and description columns (NEW)")
print("   5. Stop after finding 200 total jobs")
print("\n🚀 Run with: python scraper.py")
