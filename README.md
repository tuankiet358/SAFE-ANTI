<div align="center">

<h1>SAFE-ANTI 2.0</h1>

<p><b>Comprehensive Discord Server Security and AutoMod Solution — High Performance and Professional</b></p>

<p>
  <a href="https://discord.gg/6uEa3eBdkn">
    <img src="https://img.shields.io/badge/DOWNLOAD_RELEASE_ZIP-2ea44f?style=for-the-badge&logoColor=white" alt="Download Release ZIP" />
  </a>
  &nbsp;
  <a href="https://github.com/tuankiet358/SAFE-ANTI/releases/latest">
    <img src="https://img.shields.io/badge/VIEW_LATEST_RELEASE-0969da?style=for-the-badge&logoColor=white" alt="Latest Release" />
  </a>
  &nbsp;
  <a href="https://discord.gg/cyY8yRvzR6">
    <img src="https://img.shields.io/badge/JOIN_DISCORD-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server" />
  </a>
</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/discord.py-v2-5865F2?style=flat-square&logo=discord&logoColor=white" alt="discord.py v2" />
  <img src="https://img.shields.io/badge/Architecture-Modular%20Cog-orange?style=flat-square" alt="Modular Cog Architecture" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square" alt="License GPL-3.0" />
</p>

</div>

---

## Overview

**SAFE-ANTI 2.0** is a specialized Discord bot system engineered for server security and moderation. Built on Python with **discord.py v2** and a modern **Modular/Cog architecture**, it delivers multi-layered protection against server nuking, controls disruptive members, integrates Discord's native AutoMod API, and provides an interactive in-Discord UI dashboard powered by Buttons and Select Menus.

---

## Key Features

| Feature | Description |
|---|---|
| **Anti-Nuke / Anti-Raid** | Instantly detects and prevents mass channel deletions, unauthorized bans/kicks, and illicit server configuration changes. |
| **Native Discord AutoMod** | Deep integration with Discord's AutoMod API to neutralize spam and malicious links within milliseconds. |
| **Interactive UI/UX** | In-Discord control panel using Dropdown Menus and Buttons for effortless configuration — no complex commands required. |
| **Detailed Logging System** | Records all suspicious activities with rich embeds delivered to a dedicated administration log channel. |
| **Global Rate Limiter** | Automatic global cooldown mechanism to isolate and neutralize entities attempting spam or nuke raids. |

---

## Project Structure

```
SAFE-ANTI/
├── .env.example
├── .env
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── src/
    ├── main.py
    ├── config.py
    ├── global_cooldown.py
    ├── database/
    │   ├── __init__.py
    │   └── anti_settings.db
    ├── utils/
    │   ├── __init__.py
    │   ├── embed.py
    │   └── logger.py
    └── cogs/
        └── anti/
            ├── __init__.py
            ├── constants.py
            ├── helpers.py
            ├── automod.py
            ├── ui.py
            └── anti_cog.py
```

---

## How to Get Source Code

1. **Step 1:** Join our Discord server via the link: [https://discord.gg/6uEa3eBdkn](https://discord.gg/6uEa3eBdkn)
2. **Step 2:** Find the source code channel under the **"OPEN SOURCE"** category.
3. **Step 3:** Access the channel, download the source code, and extract (unzip) it.

---

## Installation and Setup

### System Requirements

- Python **3.10** or higher
- A Discord Bot Token from the [Discord Developer Portal](https://discord.com/developers/applications)

### Step 1 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Configure Environment

Copy `.env.example` to `.env` and populate the required values:

```env
DISCORD_TOKEN = your_bot_token_here
BOT_PREFIX = your_bot_prefix_here
```

### Step 3 — Run the Bot

```bash
python src/main.py
```

---

## Community and Support

<div align="center">

<p>Need help, want to report an issue, or connect with other users?<br>Join the official support server:</p>

<a href="https://discord.gg/cyY8yRvzR6">
  <img src="https://img.shields.io/badge/TWIN_CORE_DISCORD_STUDIO-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord" />
</a>

</div>

---

<div align="center">

<sub>Produced and Developed by <b>TWIN CORE</b></sub>

</div>
