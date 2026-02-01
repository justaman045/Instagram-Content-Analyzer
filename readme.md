# Instagram — Python Automation & CLI Tool

> **A Python-based Instagram automation framework** with a CLI interface, scheduling, and optional Telegram integration. Use this repository to build, test, and run automation workflows that interact with Instagram accounts (posting, monitoring, notifying). **Use at your own risk — automating actions on third-party platforms may violate their Terms of Service.**

---

## Table of Contents

- [About](#about)
- [Features](#features)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI](#cli)
  - [Running the Bot](#running-the-bot)
  - [Scheduler](#scheduler)
  - [Telegram integration (optional)](#telegram-integration-optional)
- [Database & Persistence](#database--persistence)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Security & Responsible Use](#security--responsible-use)
- [License](#license)
- [Contact](#contact)

---

## About

This project provides tooling to automate common Instagram workflows using Python. It is organized as a CLI-driven application with modular components for interacting with Instagram, managing scheduled jobs, and persisting state. There are also helper modules for integration with Telegram to receive notifications or deliver content.

Use this repository as a starting-point for:

- Building a scheduled poster or monitor for Instagram accounts
- Creating bots that monitor public accounts for new content
- Sending notifications (e.g., via Telegram) when conditions are met
- Experimenting with automation workflows and building custom scripts


## Features

- Command-line interface for quick operations and configuration
- Scheduler for running time-based jobs
- Modular Instagram interaction layer
- Simple database/persistence layer for sessions, project lists, and schedules
- Optional Telegram integration for notifications and delivery
- Utility modules for common helpers and tooling


## Repository Structure

```text
Instagram/
├─ bot.py             # Main bot entrypoint (automation logic)
├─ cli.py             # Command-line interface for the project
├─ scheduler.py       # Scheduling / cron-like runner
├─ instagram/         # Instagram interaction modules
├─ db/                # Persistence layer (SQLite / DB helpers)
├─ tgram/             # Telegram integration helpers
├─ utils/             # Utility helpers (parsers, helpers)
├─ requirements.txt   # Python dependencies (if present)
└─ README.md          # This file
```

> If your tree differs, adapt the commands below accordingly.


## Requirements

- Python 3.10+ (recommended)
- pip
- Virtualenv (recommended)

The project may require additional libraries such as `requests`, `httpx`, `python-telegram-bot`, or an Instagram automation library. A `requirements.txt` file should exist in the repo — install it using pip.


## Installation

1. Clone the repository:

```bash
git clone https://github.com/justaman045/Instagram.git
cd Instagram
```

2. Create and activate a virtual environment (Linux/macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```


## Configuration

Create a `.env` file in the project root (or set environment variables) with the values your project expects. Common variables include:

```env
# Instagram credentials / session details
IG_USERNAME=your_username
IG_PASSWORD=your_password
# Or path to session/cookies if used
IG_SESSION_FILE=./sessions/session.json

# Telegram (optional)
TG_BOT_TOKEN=123456:ABC-DEF...
TG_CHAT_ID=987654321

# DB path (if using SQLite)
DATABASE_URL=sqlite:///data/db.sqlite3
```

> **Security:** Do not commit sensitive credentials to Git. Add `.env` to `.gitignore`.


## Usage

### CLI

The repository exposes a CLI to interact with projects, run jobs, and manage monitored accounts. Basic patterns:

```bash
# Show help
python cli.py --help

# Example: list projects (if supported)
python cli.py projects list

# Example: run a command for project index 1
python cli.py monitor --project 1
```

> Replace subcommands according to the actual `cli.py --help` output.


### Running the Bot

Run the main bot entrypoint to start the automation logic:

```bash
python bot.py
```

Monitor logs and output in the terminal. Use a process manager (systemd, pm2, supervisor) for production to keep the process alive.


### Scheduler

If the repo includes a `scheduler.py` or similar, this is used to run periodic tasks (e.g., every hour). Example:

```bash
python scheduler.py
```

For production scheduling, prefer GitHub Actions, systemd timers, or cron — or implement a recurring job via `schedule`, `APScheduler`, or a cloud scheduler.


### Telegram integration (optional)

If you configure `TG_BOT_TOKEN` and `TG_CHAT_ID`, the bot can send updates or deliver reels to your Telegram. Common flows:

- Send best-performing reels to the configured chat at scheduled times
- Receive interactive messages to download captions or copies


## Database & Persistence

The `db/` folder contains helpers for storing projects, monitored accounts, sessions, and run history. Common approaches:

- SQLite for single-user/local setups
- Postgres or Supabase for multi-user or cloud deployments

If the repo expects a specific migration or schema, run the provided migration script (if any), or check `db/schema.sql` for table definitions.


## Development

- Write unit tests for Instagram interaction code (network calls must be mocked)
- Keep credentials out of source control — use `.env` files or secrets management
- Use `pre-commit` hooks and linters (flake8 / isort / black) for consistent style


## Troubleshooting

- **Instagram blocks / 401/403/429 responses**: Instagram is strict about automation. Handle rate limits, backoff, and rotate sessions/IPs.
- **Session/auth failures**: Verify your credentials and session file. Consider using a headless browser session for login if necessary.
- **Telegram notifications missing**: Check `TG_BOT_TOKEN` and `TG_CHAT_ID` and verify the bot has permission to send messages to the chat.
- **DB errors**: Confirm `DATABASE_URL` points to a writeable location and required tables exist.


## Contributing

Contributions are welcome. Suggested workflow:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Add tests for your changes
4. Open a pull request with a clear description

Please avoid committing secrets or private keys.


## Deployment

## Deployment

## Deployment: Dual Mode Strategy

To keep the system robust and decoupled, this repository separates **Core Logic** from **User Interaction**.

### 1. The Engine (Runs Automatically)
-   **Script**: `core_runner.py`
-   **Schedule**: Runs every 6 hours on GitHub Actions.
-   **Job**: Monitor -> Analyze -> Deliver.
-   **Behavior**: It processes all active projects in a batch and then exits. It does **not** listen for Telegram commands.

### 2. The Interface (Runs On-Demand)
-   **Script**: `bot.py` (Manager Bot)
-   **Trigger**:
    -   **Doorbell**: When you message the bot, Google Apps Script triggers GHA.
    -   **Manual**: Trigger "Run workflow" -> select Mode: `bot`.
-   **Behavior**: It wakes up for 5-15 minutes to let you **add/remove accounts**. It does **not** process reels.

### Setup "Wake on Message" (Doorbell)
Since GHA is passive, we use a free Google Apps Script bridge.

1.  **Get a GitHub Token**: [Generate Classic Token](https://github.com/settings/tokens) (`repo` scope).
2.  **Create Script**: [script.google.com](https://script.google.com) -> Paste `resources/telegram_bridge.js`.
3.  **Configure**: Fill in `GITHUB_TOKEN`, `Repo Name`, and `Bot Token`.
4.  **Deploy**: Publish as Web App -> Access: "Anyone".
5.  **Connect**: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WEB_APP_URL>`

**Result**:
-   **Schedule**: Analysis happens silently in the background.
-   **Message**: The bot wakes up instantly to manage your accounts.

### VPS / Server (True 24/7)
For true continuous uptime (instant replies), deploy to a VPS:

1. Clone repo & install deps.
2. Run with a process manager like `pm2`:
   ```bash
   # Set runtime to 0 or remove the env var to run forever
   pm2 start bot.py --name instagram-bot --interpreter python3
   ```


## Security & Responsible Use

- Automating actions on Instagram may violate Instagram’s Terms of Service. This project is provided for educational purposes. The author is not responsible for any account bans or legal issues.
- Rate-limit your requests and implement exponential backoff to reduce the risk of being flagged.


## License

Include a license file (e.g. `LICENSE`) in the repo. If you don’t have one yet, consider using MIT:

```
MIT License
Copyright (c) [YEAR] [OWNER]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```


## Contact

If you have questions or want help improving the project, open an issue or reach out via GitHub profile: `https://github.com/justaman045`.

---

*Happy hacking — and remember to use automation responsibly.*

