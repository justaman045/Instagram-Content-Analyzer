import questionary
from rich import print
from db.supabase_client import supabase
from utils.time import get_timezone

def run_setup():
    print("\n[bold cyan]🚀 Insta Reel Intelligence – Project Setup[/bold cyan]\n")

    # -----------------------------
    # Project Info
    # -----------------------------
    project_name = questionary.text(
        "Project name (e.g. Fitness Reels):"
    ).ask()

    destination_ig = questionary.text(
        "Your Instagram username (optional, label only):"
    ).ask()

    user_id = questionary.text(
        "Your Supabase user_id (from auth.users):"
    ).ask()

    project = supabase.table("projects").insert({
        "name": project_name,
        "destination_instagram": destination_ig,
        "user_id": user_id
    }).execute()

    project_id = project.data[0]["id"]
    print(f"[green]✅ Project created:[/green] {project_name}")

    # -----------------------------
    # Instagram Accounts
    # -----------------------------
    print("\n[bold]Add Instagram accounts to monitor[/bold]")
    while True:
        username = questionary.text(
            "Instagram username (without @):"
        ).ask()

        supabase.table("monitored_accounts").insert({
            "project_id": project_id,
            "ig_username": username
        }).execute()

        more = questionary.confirm(
            "Add another account?"
        ).ask()

        if not more:
            break

    # -----------------------------
    # Rules
    # -----------------------------
    print("\n[bold]Performance Rules[/bold]")

    min_views = questionary.text(
        "Minimum views to qualify (e.g. 1000):",
        default="1000"
    ).ask()

    window = questionary.text(
        "Time window in hours:",
        default="24"
    ).ask()

    supabase.table("rules").insert({
        "project_id": project_id,
        "min_views": int(min_views),
        "window_hours": int(window)
    }).execute()

    # -----------------------------
    # Delivery Settings
    # -----------------------------
    print("\n[bold]Delivery Settings[/bold]")

    send_hour = questionary.text(
        "Send hour (0–23, local time):",
        default="21"
    ).ask()

    supabase.table("delivery_settings").insert({
        "project_id": project_id,
        "send_hour": int(send_hour),
        "timezone": get_timezone(),
        "max_reels": 1
    }).execute()

    # -----------------------------
    # Telegram Setup
    # -----------------------------
    print("\n[bold]Telegram Setup[/bold]")

    telegram_user_id = questionary.text(
        "Your Telegram user_id:"
    ).ask()

    chat_id = questionary.text(
        "Telegram chat_id (usually same as user_id):"
    ).ask()

    supabase.table("telegram_accounts").insert({
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id
    }).execute()

    print("\n[bold green]🎉 Setup Complete![/bold green]")
    print("You can now run:")
    print("  👉 python cli.py monitor")
