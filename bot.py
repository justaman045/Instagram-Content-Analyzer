import os
import re
import json
import logging
from typing import Optional

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

from db.supabase_client import supabase

# ======================================================
# CONFIG
# ======================================================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telegram-webhook")

# ======================================================
# MARKDOWN SAFETY
# ======================================================
def md_escape(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# ======================================================
# HELPERS
# ======================================================
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

# ======================================================
# SUPABASE SESSION HELPERS
# ======================================================
def get_session(chat_id: str):
    return (
        supabase.table("telegram_sessions")
        .select("*")
        .eq("chat_id", chat_id)
        .maybe_single()
        .execute()
        .data
    )

def save_session(chat_id: str, stage: str, payload: dict):
    supabase.table("telegram_sessions").upsert({
        "chat_id": chat_id,
        "stage": stage,
        "payload": payload,
    }).execute()

def clear_session(chat_id: str):
    supabase.table("telegram_sessions").delete().eq("chat_id", chat_id).execute()

# ======================================================
# TELEGRAM HANDLER
# ======================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    chat_id = str(msg.chat.id)
    text = msg.text.strip()

    session = get_session(chat_id)

    # ---------------- PROJECT SELECTION ----------------
    if session and session.get("stage") == "project":
        payload = session["payload"]
        projects = payload["projects"]

        try:
            idx = int(text) - 1
            project = projects[idx]
        except Exception:
            await msg.reply_text(
                "❌ Invalid selection\\. Try again\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        ig = payload["ig"]

        row = (
            supabase.table("monitored_accounts")
            .select("id, ig_username")
            .eq("project_id", project["id"])
            .maybe_single()
            .execute()
            .data
        )

        if not row:
            supabase.table("monitored_accounts").insert({
                "project_id": project["id"],
                "ig_username": ig,
            }).execute()
        else:
            existing = [u.strip() for u in (row.get("ig_username") or "").split(",") if u.strip()]
            if ig not in existing:
                existing.append(ig)
                supabase.table("monitored_accounts").update({
                    "ig_username": ", ".join(existing)
                }).eq("id", row["id"]).execute()

        await msg.reply_text(
            f"✅ *@{md_escape(ig)}* added to *{md_escape(project['name'])}*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        clear_session(chat_id)
        return

    # ---------------- NEW IG USERNAME ----------------
    ig = extract_ig_username(text)
    if not ig:
        return

    telegram_account = (
        supabase.table("telegram_accounts")
        .select("user_id")
        .eq("chat_id", chat_id)
        .maybe_single()
        .execute()
        .data
    )

    if not telegram_account:
        await msg.reply_text(
            "❌ Please complete setup first\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    projects = (
        supabase.table("projects")
        .select("id,name")
        .eq("user_id", telegram_account["user_id"])
        .eq("active", True)
        .execute()
        .data
    )

    if not projects:
        await msg.reply_text(
            "❌ No active projects found\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    reply = f"Choose a project for *@{md_escape(ig)}*:\n\n"
    for i, p in enumerate(projects, 1):
        reply += f"{i}\\. {md_escape(p['name'])}\n"

    save_session(chat_id, "project", {"ig": ig, "projects": projects})
    await msg.reply_text(reply, parse_mode=ParseMode.MARKDOWN_V2)

# ======================================================
# FASTAPI + TELEGRAM APP
# ======================================================
app = FastAPI()

telegram_app = Application.builder().token(BOT_TOKEN).build()
telegram_app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
)

@app.on_event("startup")
async def startup():
    log.info("Initializing Telegram application...")
    await telegram_app.initialize()

@app.post("/api/bot")
async def telegram_webhook(request: Request):
    if WEBHOOK_SECRET:
        secret = request.headers.get("x-telegram-bot-api-secret-token")
        if secret != WEBHOOK_SECRET:
            return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def health():
    return {"status": "alive"}
