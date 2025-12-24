# telegram/bot.py

import os
import re
import logging
from typing import Dict, List, Optional

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
# MARKDOWN SAFETY (Telegram MarkdownV2)
# ==========================
def md_escape(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# ==========================
# HELPERS
# ==========================
def extract_ig_username(text: str) -> Optional[str]:
    text = text.strip()

    if "instagram.com" in text:
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", text)
        return m.group(1) if m else None

    if text.startswith("@"):
        return text[1:]

    if re.fullmatch(r"[A-Za-z0-9_.]+", text):
        return text

    return None


async def reply_project_list(msg, title: str, projects: List[dict]):
    reply = f"{title}\n\n"
    for i, p in enumerate(projects, 1):
        reply += f"{i}\\. {md_escape(p['name'])}\n"
    await msg.reply_text(reply, parse_mode="MarkdownV2")

# ==========================
# MAIN HANDLER
# ==========================
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    telegram_user_id = str(msg.from_user.id)
    text = (msg.text or "").strip()

    # ==========================
    # COMMANDS
    # ==========================
    if text == "/list":
        await handle_list(msg, telegram_user_id)
        return

    if text == "/remove":
        await handle_remove_start(msg, telegram_user_id)
        return

    if text == "/cancel":
        PENDING.pop(telegram_user_id, None)
        await msg.reply_text("✅ Cancelled", parse_mode="MarkdownV2")
        return
    
    if text in ("/stop", "/cancel"):
        PENDING.pop(telegram_user_id, None)
        await msg.reply_text(
            "🛑 Current action stopped\\. You can start again\\.",
            parse_mode="MarkdownV2",
        )
        return


    # ==========================
    # ADD FLOW — ACCOUNT PICK
    # ==========================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "add_user":
        state = PENDING[telegram_user_id]
        try:
            idx = int(text) - 1
            acc = state["accounts"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection", parse_mode="MarkdownV2")
            return

        state["stage"] = "add_project"
        state["user_id"] = acc["user_id"]
        state["projects"] = acc["projects"]

        await reply_project_list(
            msg,
            f"Add *@{md_escape(state['ig'])}* to:",
            acc["projects"],
        )
        return

    # ==========================
    # ADD FLOW — PROJECT PICK
    # ==========================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "add_project":
        state = PENDING[telegram_user_id]
        try:
            idx = int(text) - 1
            project = state["projects"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection", parse_mode="MarkdownV2")
            return

        ig = state["ig"]

        row = (
            supabase.table("monitored_accounts")
            .select("id, ig_username")
            .eq("project_id", project["id"])
            .single()
            .execute()
            .data
        )

        if not row:
            supabase.table("monitored_accounts").insert({
                "project_id": project["id"],
                "ig_username": ig,
                "is_active": True,
            }).execute()
        else:
            existing = [u.strip() for u in row["ig_username"].split(",")]
            if ig not in existing:
                existing.append(ig)
                supabase.table("monitored_accounts").update({
                    "ig_username": ", ".join(existing)
                }).eq("id", row["id"]).execute()

        await msg.reply_text(
            f"✅ *@{md_escape(ig)}* added to *{md_escape(project['name'])}*",
            parse_mode="MarkdownV2",
        )

        del PENDING[telegram_user_id]
        return

    # ==========================
    # REMOVE FLOW — PROJECT PICK
    # ==========================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "remove_project":
        state = PENDING[telegram_user_id]
        try:
            idx = int(text) - 1
            project = state["projects"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection", parse_mode="MarkdownV2")
            return

        rows = (
            supabase.table("monitored_accounts")
            .select("id, ig_username")
            .eq("project_id", project["id"])
            .execute()
            .data or []
        )

        usernames = []
        for r in rows:
            for u in r["ig_username"].split(","):
                usernames.append(u.strip())

        if not usernames:
            await msg.reply_text("ℹ️ No monitored accounts", parse_mode="MarkdownV2")
            del PENDING[telegram_user_id]
            return

        state["stage"] = "remove_user"
        state["rows"] = rows
        state["usernames"] = usernames

        reply = "Choose username to remove:\n\n"
        for i, u in enumerate(usernames, 1):
            reply += f"{i}\\. @{md_escape(u)}\n"

        await msg.reply_text(reply, parse_mode="MarkdownV2")
        return

    # ==========================
    # REMOVE FLOW — USER PICK
    # ==========================
    if telegram_user_id in PENDING and PENDING[telegram_user_id]["stage"] == "remove_user":
        state = PENDING[telegram_user_id]
        try:
            idx = int(text) - 1
            username = state["usernames"][idx]
        except Exception:
            await msg.reply_text("❌ Invalid selection", parse_mode="MarkdownV2")
            return

        for r in state["rows"]:
            existing = [u.strip() for u in r["ig_username"].split(",")]
            if username in existing:
                existing.remove(username)
                if not existing:
                    supabase.table("monitored_accounts").delete().eq("id", r["id"]).execute()
                else:
                    supabase.table("monitored_accounts").update({
                        "ig_username": ", ".join(existing)
                    }).eq("id", r["id"]).execute()
                break

        await msg.reply_text(
            f"🗑️ *@{md_escape(username)}* removed",
            parse_mode="MarkdownV2",
        )

        del PENDING[telegram_user_id]
        return

    # ==========================
    # NEW MESSAGE → TRY ADD IG USERNAME
    # ==========================
    ig_username = extract_ig_username(text)
    if not ig_username:
        return

    telegram_accounts = (
        supabase.table("telegram_accounts")
        .select("user_id")
        .eq("chat_id", telegram_user_id)
        .execute()
        .data
    )

    if not telegram_accounts:
        await msg.reply_text("❌ Please complete setup first", parse_mode="MarkdownV2")
        return

    accounts = []
    for row in telegram_accounts:
        projects = (
            supabase.table("projects")
            .select("id,name,destination_instagram")
            .eq("user_id", row["user_id"])
            .eq("active", True)
            .execute()
            .data or []
        )

        if not projects:
            continue

        dest = projects[0].get("destination_instagram") or "unknown"
        label = f"@{dest} — {len(projects)} project{'s' if len(projects) != 1 else ''}"

        accounts.append({
            "user_id": row["user_id"],
            "projects": projects,
            "label": label,
        })

    if not accounts:
        await msg.reply_text("❌ No active projects found", parse_mode="MarkdownV2")
        return

    # MULTIPLE ACCOUNTS
    if len(accounts) > 1:
        PENDING[telegram_user_id] = {
            "stage": "add_user",
            "ig": ig_username,
            "accounts": accounts,
        }

        reply = "Choose account:\n\n"
        for i, acc in enumerate(accounts, 1):
            reply += f"{i}\\. {md_escape(acc['label'])}\n"

        await msg.reply_text(reply, parse_mode="MarkdownV2")
        return

    # SINGLE ACCOUNT
    PENDING[telegram_user_id] = {
        "stage": "add_project",
        "ig": ig_username,
        "user_id": accounts[0]["user_id"],
        "projects": accounts[0]["projects"],
    }

    await reply_project_list(
        msg,
        f"Add *@{md_escape(ig_username)}* to:",
        accounts[0]["projects"],
    )

# ==========================
# LIST HANDLER
# ==========================
async def handle_list(msg, telegram_user_id: str):
    telegram_accounts = (
        supabase.table("telegram_accounts")
        .select("user_id")
        .eq("chat_id", telegram_user_id)
        .execute()
        .data
    )

    if not telegram_accounts:
        await msg.reply_text("❌ Setup required", parse_mode="MarkdownV2")
        return

    reply = "📋 *Monitored Accounts*\n\n"

    for row in telegram_accounts:
        projects = (
            supabase.table("projects")
            .select("id,name")
            .eq("user_id", row["user_id"])
            .execute()
            .data or []
        )

        for p in projects:
            rows = (
                supabase.table("monitored_accounts")
                .select("ig_username")
                .eq("project_id", p["id"])
                .execute()
                .data or []
            )

            reply += f"*{md_escape(p['name'])}*\n"
            if not rows:
                reply += "_No accounts_\n\n"
                continue

            for r in rows:
                for u in r["ig_username"].split(","):
                    reply += f"• @{md_escape(u.strip())}\n"
            reply += "\n"

    await msg.reply_text(reply, parse_mode="MarkdownV2")

# ==========================
# REMOVE START
# ==========================
async def handle_remove_start(msg, telegram_user_id: str):
    telegram_accounts = (
        supabase.table("telegram_accounts")
        .select("user_id")
        .eq("chat_id", telegram_user_id)
        .execute()
        .data
    )

    if not telegram_accounts:
        await msg.reply_text("❌ Setup required", parse_mode="MarkdownV2")
        return

    projects = []
    for row in telegram_accounts:
        rows = (
            supabase.table("projects")
            .select("id,name")
            .eq("user_id", row["user_id"])
            .execute()
            .data or []
        )
        projects.extend(rows)

    if not projects:
        await msg.reply_text("❌ No projects found", parse_mode="MarkdownV2")
        return

    PENDING[telegram_user_id] = {
        "stage": "remove_project",
        "projects": projects,
    }

    await reply_project_list(msg, "Choose project to remove from:", projects)

# ==========================
# ERROR HANDLER
# ==========================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled exception", exc_info=context.error)

# ==========================
# START BOT
# ==========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, on_message))
    app.add_error_handler(on_error)

    log.info("🤖 Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
