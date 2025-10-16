"""
Bot information and configuration constants
"""
import os

# Bot usernames for link generation (always use boltarhegabot as requested by user)
BOT_USERNAMES = ['@boltarhegabot']

# File store channel - use the target channel as file store
FILE_STORE_CHANNEL = [os.getenv('TARGET_CHANNEL_ID', "-1002818242381")]