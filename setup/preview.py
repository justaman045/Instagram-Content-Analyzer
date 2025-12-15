import questionary
from rich import print
from rich.panel import Panel
from rich.json import JSON
from utils.time import get_timezone
from uuid import uuid4

def run_preview():
    print("\n[bold cyan]🧪 Insta Reel Intelligence – PREVIEW MODE[/bold cyan]")
    print("[dim]No data will be saved. This is a dry run.[/dim]\n")

    # -----------------------------
    # Project Info
    # -----------------------------
    project_name = questionary.text(
        "Project name:"
    ).ask()

    destination_ig = questionary.text(
        "Destination Instagram username (label only):"
    ).ask()

    user_id = questionary.text(
        "Supabase user_id (owner):"
    ).ask()

    project_id = str(uuid4())

    project_payload = {
        "id": project_id,
        "user_id": user_id,
        "name": project_name,
        "destination_instagram": destination_ig,
        "created_at": "NOW()"
    }

    # -----------------------------
    # Monitored Accounts
    # -----------------------------
    monitored_accounts = []

    print("\n[bold]Instagram accounts to monitor[/bold]")
    while True:
        username = questionary.text(
            "Instagram username (without @):"
        ).ask()

        monitored_accounts.append({
            "id": str(uuid4()),
            "project_id": project_id,
            "ig_username": username,
            "is_active": True,
            "created_at": "NOW()"
        })

        if not questionary.confirm("Add another account?").ask():
            break

    # -----------------------------
    # Rules
    # -----------------------------
    print("\n[bold]Performance rules[/bold]")

    min_views = int(questionary.text(
        "Minimum views:",
        default="1000"
    ).ask())

    window_hours = int(questionary.text(
        "Time window (hours):",
        default="24"
    ).ask())

    rules_payload = {
        "id": str(uuid4()),
        "project_id": project_id,
        "min_views": min_views,
        "window_hours": window_hours,
        "created_at": "NOW()"
    }

    # -----------------------------
    # Delivery Settings
    # -----------------------------
    print("\n[bold]Delivery settings[/bold]")

    send_hour = int(questionary.text(
        "Send hour (0–23):",
        default="21"
    ).ask())

    delivery_payload = {
        "id": str(uuid4()),
        "project_id": project_id,
        "send_hour": send_hour,
        "timezone": get_timezone(),
        "max_reels": 1,
        "created_at": "NOW()"
    }

    # -----------------------------
    # Telegram Setup
    # -----------------------------
    print("\n[bold]Telegram delivery[/bold]")

    telegram_user_id = questionary.text(
        "Telegram user_id:"
    ).ask()

    chat_id = questionary.text(
        "Telegram chat_id:"
    ).ask()

    telegram_payload = {
        "id": str(uuid4()),
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "created_at": "NOW()"
    }

    # -----------------------------
    # FINAL PREVIEW OUTPUT
    # -----------------------------
    print("\n[bold green]📦 FINAL DATA PREVIEW[/bold green]\n")

    print(Panel(JSON.from_data(project_payload), title="projects"))
    print(Panel(JSON.from_data(monitored_accounts), title="monitored_accounts"))
    print(Panel(JSON.from_data(rules_payload), title="rules"))
    print(Panel(JSON.from_data(delivery_payload), title="delivery_settings"))
    print(Panel(JSON.from_data(telegram_payload), title="telegram_accounts"))

    print("\n[bold yellow]ℹ️ Nothing was saved to the database.[/bold yellow]")
    print("[dim]Use `python cli.py setup` when you are ready to persist this data.[/dim]\n")
