<div align="center">

  # 🛡️ SAFE-ANTI DISCORD BOT
**A comprehensive, optimized, and professional Discord server protection and moderation solution.**
Python Version

Discord.py

License: MIT
</div>

## 📖 About The Project
**SAFE-ANTI** is a security-focused Discord bot developed in **Python** (discord.py v2) utilizing a modern **Modular/Cog Framework**. It is designed to safeguard your server against raids, spam, and malicious actions, while seamlessly integrating Discord Native AutoMod tools and intuitive UI components.

## ✨ Key Features
 
 * 🚀 **Anti-Nuke & Anti-Raid**: Detects and instantly blocks destructive actions like channel deletion, mass kicking, or mass banning.

 * 🤖 **Discord AutoMod Integration**: Connects directly with Discord Native AutoMod API for high-speed rule enforcement.
 
 * 🎛️ **Interactive UI/UX**: Easily adjust configurations and toggle modules via interactive **Select Menus** and **Buttons**.
 
 * 📊 **Detailed Logging**: Records key events through clean, beautifully formatted Embeds.
 
 * ⚡ **Modular Architecture**: Well-structured code hierarchy (Src/), designed for effortless maintenance and scalability.

## 📂 Project Structure
.
├── .env.example            
├── .gitignore              
├── README.md               
├── requirements.txt        
└── Src/

├── config.py          
├── main.py             
├── utils/
│        ├── embed.py        
│        └── logger.py       

└── cogs/
└── anti/  

├── constants.py
├── helpers.py  
├── automod.py  
├── ui.py       
└── cog.py      

## 🚀 Getting Started

### 1. Prerequisites
 * **Python 3.10** or higher.
 * A Bot Token created on the Discord Developer Portal.

### 2. Dependency Installation
Install all required packages via requirements.txt:
pip install -r requirements.txt

### 3. Environment Setup
Create a .env file based on .env.example and fill in your Bot Token:
DISCORD_TOKEN=your_bot_token_here
BOT_PREFIX=!

### 4. Running the Bot
python Src/main.py

## 📜 License
Distributed under the **MIT License**. See LICENSE for details.
<div align="center">
<sub>Made with ❤️ for Discord Communities</sub>
</div>
