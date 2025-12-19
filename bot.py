# telegram/bot.py

import os
import re
import logging
from typing import Dict, List

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from db.supabase_client import supabase

# ==========================
# LOGGING
# ==========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telegram-bot")

# Silence noisy libraries
for lib in ("httpx", "httpcore", "postgrest", "supabase", "urllib3"):
    logging.getLogger(lib).setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# ==========================
# IN-MEMORY STATE
# ==========================
PENDING: Dict[str, dict] = {}

# ==========================
# HELPERS
# ==========================
def extract_ig_username(text: str) -> str | None:
    text = text.strip()

    if "instagram.com" in text:
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", text)
        return m.group(1) if m else None

    if text.startswith("@"):
        return text[1:]

    if re.fullmatch(r"[A-Za-z0-9_.]+", text):
        return text

    return None


async def reply_project_list(message, ig: str, projects: List[dict]):
    reply = f"Which project do you want to add @{ig} to?\n\n"
    for i, p in enumerate(projects, 1):
        reply += f"{i}. {p['name']}\n"
    await message.reply_text(reply)


# ==========================
# MAIN HANDLER
# ==========================
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    telegram_user_id = str(msg.from_user.id)
    text = msg.text.strip()

    # ======================================================
    # STAGE 1 — ACCOUNT SELECTION
    # ======================================================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "user":
        state = PENDING[telegram_user_id]

        try:
            idx = int(text) - 1
            selected = state["accounts"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection. Try again.")
            return

        state["user_id"] = selected["user_id"]
        state["projects"] = selected["projects"]
        state["stage"] = "project"

        await reply_project_list(msg, state["ig_username"], selected["projects"])
        return

    # ======================================================
    # STAGE 2 — PROJECT SELECTION
    # ======================================================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "project":
        state = PENDING[telegram_user_id]

        try:
            idx = int(text) - 1
            project = state["projects"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection. Try again.")
            return

        ig = state["ig_username"]

        # ---------------------------------------------
        # FETCH EXISTING MONITORED_ACCOUNTS ROW
        # ---------------------------------------------
        row = (
            supabase
            .table("monitored_accounts")
            .select("id, ig_username")
            .eq("project_id", project["id"])
            .single()
            .execute()
            .data
        )

        # ---------------------------------------------
        # NO ROW → CREATE
        # ---------------------------------------------
        if not row:
            supabase.table("monitored_accounts").insert({
                "project_id": project["id"],
                "ig_username": ig,
                "is_active": True,
            }).execute()

            await msg.reply_text(
                f"✅ @{ig} added to *{project['name']}*",
                parse_mode="Markdown",
            )

        # ---------------------------------------------
        # ROW EXISTS → APPEND
        # ---------------------------------------------
        else:
            existing = [
                u.strip()
                for u in (row["ig_username"] or "").split(",")
                if u.strip()
            ]

            if ig in existing:
                await msg.reply_text(
                    f"⚠️ @{ig} already exists in *{project['name']}*",
                    parse_mode="Markdown",
                )
            else:
                existing.append(ig)
                updated = ", ".join(existing)

                supabase.table("monitored_accounts").update({
                    "ig_username": updated
                }).eq("id", row["id"]).execute()

                await msg.reply_text(
                    f"✅ @{ig} added to *{project['name']}*",
                    parse_mode="Markdown",
                )

        del PENDING[telegram_user_id]
        return

    # ======================================================
    # NEW MESSAGE → TRY IG USERNAME
    # ======================================================
    ig_username = extract_ig_username(text)
    if not ig_username:
        return

    # ------------------------------------------------------
    # Resolve Telegram → Supabase users
    # ------------------------------------------------------
    telegram_accounts = (
        supabase
        .table("telegram_accounts")
        .select("user_id")
        .eq("chat_id", telegram_user_id)
        .execute()
        .data
    )

    if not telegram_accounts:
        await msg.reply_text("❌ Please complete setup first.")
        return

    # ------------------------------------------------------
    # Build labeled accounts
    # ------------------------------------------------------
    accounts = []

    for row in telegram_accounts:
        projects = (
            supabase
            .table("projects")
            .select("id,name,destination_instagram")
            .eq("user_id", row["user_id"])
            .eq("active", True)
            .execute()
            .data
        )

        if not projects:
            continue

        dest = projects[0].get("destination_instagram") or "unknown"
        label = f"@{dest} ({len(projects)} project{'s' if len(projects) > 1 else ''})"

        accounts.append({
            "user_id": row["user_id"],
            "projects": projects,
            "label": label,
        })

    if not accounts:
        await msg.reply_text("❌ No active projects found.")
        return

    # ======================================================
    # MULTIPLE ACCOUNTS
    # ======================================================
    if len(accounts) > 1:
        PENDING[telegram_user_id] = {
            "ig_username": ig_username,
            "accounts": accounts,
            "stage": "user",
        }

        reply = f"Multiple accounts found.\nWhich account should manage @{ig_username}?\n\n"
        for i, acc in enumerate(accounts, 1):
            reply += f"{i}. {acc['label']}\n"

        await msg.reply_text(reply)
        return

    # ======================================================
    # SINGLE ACCOUNT → PROJECT PICK
    # ======================================================
    PENDING[telegram_user_id] = {
        "ig_username": ig_username,
        "user_id": accounts[0]["user_id"],
        "projects": accounts[0]["projects"],
        "stage": "project",
    }

    await reply_project_list(msg, ig_username, accounts[0]["projects"])


# ==========================
# START BOT
# ==========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, on_message))
    log.info("🤖 Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()