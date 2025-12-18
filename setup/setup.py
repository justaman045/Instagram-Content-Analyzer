# setup/setup.py

import questionary
from rich import print
from rich.panel import Panel

from db.supabase_client import supabase
from utils.time import get_timezone


# ==========================
# HELPERS
# ==========================
def ask_text(prompt, *, default=None, required=True):
    while True:
        if default is not None:
            val = questionary.text(prompt, default=str(default)).ask()
        else:
            val = questionary.text(prompt).ask()

        if val is None:
            raise KeyboardInterrupt

        val = val.strip()

        if val or not required:
            return val

        print("[red]This field is required.[/red]")


def ask_int(prompt, *, default=None, min_val=None, max_val=None):
    while True:
        if default is not None:
            val = questionary.text(prompt, default=str(default)).ask()
        else:
            val = questionary.text(prompt).ask()

        if val is None:
            raise KeyboardInterrupt

        try:
            num = int(val)

            if min_val is not None and num < min_val:
                raise ValueError

            if max_val is not None and num > max_val:
                raise ValueError

            return num

        except ValueError:
            print("[red]Please enter a valid number.[/red]")



def confirm(prompt):
    val = questionary.confirm(prompt).ask()
    if val is None:
        raise KeyboardInterrupt
    return val


# ==========================
# MAIN SETUP
# ==========================
def run_setup():
    print(
        Panel.fit(
            "🚀 Insta Reel Intelligence\n[dim]Project Setup Wizard[/dim]",
            style="bold cyan",
        )
    )

    try:
        # -----------------------------
        # Project Info
        # -----------------------------
        project_name = ask_text(
            "Project name (e.g. Fitness Reels):"
        )

        destination_ig = ask_text(
            "Your Instagram username (label only, optional):",
            required=False,
        )

        user_id = ask_text(
            "Your Supabase user_id (from auth.users):"
        )

        # -----------------------------
        # Instagram Accounts
        # -----------------------------
        print("\n[bold]📡 Instagram Accounts to Monitor[/bold]")
        accounts = []

        while True:
            username = ask_text(
                "Instagram username (without @):"
            ).lstrip("@")

            accounts.append(username)

            if not confirm("Add another account?"):
                break

        # -----------------------------
        # Rules
        # -----------------------------
        print("\n[bold]📊 Performance Rules[/bold]")

        min_views = ask_int(
            "Minimum views to qualify:",
            default=1000,
            min_val=1,
        )

        window_hours = ask_int(
            "Time window in hours:",
            default=24,
            min_val=1,
        )

        # -----------------------------
        # Delivery Settings
        # -----------------------------
        print("\n[bold]📦 Delivery Settings[/bold]")

        send_hour = ask_int(
            "Send hour (0–23, local time):",
            default=21,
            min_val=0,
            max_val=23,
        )

        timezone = get_timezone()

        # -----------------------------
        # Telegram Setup
        # -----------------------------
        print("\n[bold]💬 Telegram Setup[/bold]")

        telegram_user_id = ask_text(
            "Your Telegram user_id:"
        )

        chat_id = ask_text(
            "Telegram chat_id (usually same as user_id):"
        )

        # -----------------------------
        # SUMMARY
        # -----------------------------
        print(
            Panel(
                f"""
[bold]Project:[/bold] {project_name}
[bold]IG Label:[/bold] {destination_ig or "-"}
[bold]Accounts:[/bold] {", ".join(accounts)}
[bold]Min Views:[/bold] {min_views}
[bold]Window:[/bold] {window_hours} hours
[bold]Send Hour:[/bold] {send_hour}:00 ({timezone})
""",
                title="Review Configuration",
                style="cyan",
            )
        )

        if not confirm("Proceed with setup?"):
            print("[yellow]Setup cancelled.[/yellow]")
            return

        # -----------------------------
        # DB INSERTS (ORDERED)
        # -----------------------------
        project = supabase.table("projects").insert(
            {
                "name": project_name,
                "destination_instagram": destination_ig,
                "user_id": user_id,
                "active": True,
            }
        ).execute()

        project_id = project.data[0]["id"]

        for username in accounts:
            supabase.table("monitored_accounts").insert(
                {
                    "project_id": project_id,
                    "ig_username": username,
                }
            ).execute()

        supabase.table("rules").insert(
            {
                "project_id": project_id,
                "min_views": min_views,
                "window_hours": window_hours,
            }
        ).execute()

        supabase.table("delivery_settings").insert(
            {
                "project_id": project_id,
                "send_hour": send_hour,
                "timezone": timezone,
                "max_reels": 1,
            }
        ).execute()

        supabase.table("telegram_accounts").upsert(
            {
                "user_id": user_id,
                "telegram_user_id": telegram_user_id,
                "chat_id": chat_id,
            },
            on_conflict="user_id,chat_id"
        ).execute()


        print("\n[bold green]🎉 Setup Complete![/bold green]")
        print("You can now run:")
        print("  👉 [cyan]python cli.py monitor[/cyan]")

    except KeyboardInterrupt:
        print("\n[yellow]Setup aborted by user.[/yellow]")
