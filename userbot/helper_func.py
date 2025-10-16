"""
Helper functions for the userbot
"""
import base64
import logging

logger = logging.getLogger(__name__)

async def encode(string):
    """Encode string to base64 using urlsafe method (EXACTLY like your commands.py)"""
    try:
        # Use urlsafe_b64encode exactly like in your commands.py
        encoded_bytes = base64.urlsafe_b64encode(string.encode('utf-8'))
        return encoded_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding text: {e}")
        return None

def decode(base64_string):
    """Decode base64 string EXACTLY like your commands.py"""
    try:
        # Add padding EXACTLY like in your commands.py: data + "=" * (-len(data) % 4)
        padded_string = base64_string + "=" * (-len(base64_string) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_string.encode('utf-8'))
        return decoded_bytes.decode('ascii')
    except Exception as e:
        logger.error(f"Error decoding base64: {e}")
        return None

async def get_message_id(client, message):
    """Get message ID from forwarded message or link"""
    try:
        if hasattr(message, 'forward') and message.forward:
            # This is a forwarded message
            if hasattr(message.forward, 'original_fwd'):
                return message.forward.original_fwd.id
            elif hasattr(message.forward, 'id'):
                return message.forward.id

        # Try to extract from text if it's a link
        if hasattr(message, 'text') and message.text:
            # Extract message ID from t.me links
            import re
            link_pattern = r't\.me/[a-zA-Z0-9_]+/(\d+)'
            match = re.search(link_pattern, message.text)
            if match:
                return int(match.group(1))

        return None
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None

def admin(func):
    """Decorator to check if user is admin"""
    # For now, we'll implement a simple admin check
    # In a real implementation, you'd check against a list of admin IDs
    async def wrapper(client, message):
        # Skip admin check for now - implement based on your needs
        return await func(client, message)
    return wrapper