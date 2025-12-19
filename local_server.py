import json
from fastapi import FastAPI, Request
from telegram import Update
from api.bot import app  # import your webhook app

fastapi = FastAPI()

@fastapi.post("/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return {"ok": True}
