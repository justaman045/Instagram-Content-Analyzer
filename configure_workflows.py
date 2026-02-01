
import os
import re
import sys
from typing import List, Dict

from db.supabase_client import supabase

# ==========================
# CONFIG
# ==========================
TEMPLATE_PATH = ".github/workflows/project_template.yml"

def get_projects() -> List[Dict]:
    projects = (
        supabase.table("projects")
        .select("id,name,active")
        .eq("active", True)
        .order("created_at")
        .execute()
        .data or []
    )
    return projects

def prompt_project(projects: List[Dict]) -> Dict:
    print("\n📋 Available Projects:")
    for i, p in enumerate(projects, 1):
        print(f"{i}. {p['name']} (ID: {p['id']})")
    
    while True:
        choice = input("\nEnter project number to configure: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                return projects[idx]
        except ValueError:
            pass
        print("❌ Invalid selection. Try again.")

def prompt_schedule() -> str:
    print("\n⏰ Schedule Configuration:")
    print("How often should this workflow run? (in hours)")
    print("Examples: 6 = every 6 hours, 12 = twice a day, 24 = once a day")
    
    while True:
        choice = input("Enter hours (1-24): ").strip()
        try:
            hours = int(choice)
            if 1 <= hours <= 24:
                # Generate cron string: "30 */N * * *"
                # We use minute 30 to avoid top-of-the-hour congestion
                if hours == 24:
                     return "30 0 * * *" # Once a day at 00:30
                else:
                     return f"30 */{hours} * * *"
        except ValueError:
            pass
        print("❌ Invalid hours. Please enter a number between 1 and 24.")

def generate_workflow(project: Dict, cron: str):
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ Template not found at {TEMPLATE_PATH}")
        return

    with open(TEMPLATE_PATH, "r") as f:
        content = f.read()

    # 1. Update Name
    safe_name = re.sub(r'[^a-zA-Z0-9]', '', project['name'])
    new_filename = f".github/workflows/project_{safe_name}.yml"
    
    content = content.replace("name: Project Workflow Template", f"name: Bot - {project['name']}")

    # 2. Update Schedule
    # Regex find: - cron: '.*'
    content = re.sub(r"- cron: '.*'", f"- cron: '{cron}'", content)
    
    # 3. Inject Project ID
    # Find the PROJECT_ID line and inject the real ID
    # Look for: PROJECT_ID: ${{ secrets.PROJECT_ID }}
    content = content.replace(
        "PROJECT_ID: ${{ secrets.PROJECT_ID }}", 
        f"PROJECT_ID: \"{project['id']}\" # {project['name']}"
    )

    # 4. Remove Template triggers? 
    # Optional: We might want to keep manual triggers but updated.
    
    with open(new_filename, "w") as f:
        f.write(content)
        
    print(f"\n✅ Created workflow: {new_filename}")
    print(f"   • Project: {project['name']}")
    print(f"   • Schedule: Every {cron.split('/')[1].split()[0] if '/' in cron else '24'} hours")
    print("\n👉 Commit and push this file to GitHub to activate it.")

def main():
    print("🚀 GitHub Actions Workflow Generator")
    print("====================================")
    
    projects = get_projects()
    if not projects:
        print("❌ No active projects found in database.")
        return

    target = prompt_project(projects)
    cron = prompt_schedule()
    generate_workflow(target, cron)

if __name__ == "__main__":
    main()
