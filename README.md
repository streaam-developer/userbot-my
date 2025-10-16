# Telegram Userbot

This is an advanced Telegram userbot that monitors messages for specific bot links, processes them, and forwards videos to a specified channel.

## Features

- Monitors messages for specific bot username links
- Automatically joins required channels
- Forwards videos to specified target channel
- Advanced error handling and retry mechanisms
- Logging system for tracking operations
- Flood control protection

## Setup

1. Install the required packages:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file:
   - Copy `.env.example` to `.env`
   - Fill in your Telegram API credentials:
     - Get API_ID and API_HASH from https://my.telegram.org/apps
     - Set your TARGET_CHANNEL_ID (the channel where videos will be forwarded)

3. Run the userbot:
```bash
python userbot/userbot.py
```

## Error Handling

The userbot includes comprehensive error handling for:
- Channel join errors
- Flood wait limits
- Invalid links
- Network issues
- Message forwarding errors

## Logging

All operations are logged to `userbot.log` for monitoring and debugging.