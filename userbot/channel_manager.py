"""
Channel management and joining functions
"""
import asyncio
import logging

from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

logger = logging.getLogger(__name__)

class ChannelManager:
    """Handles channel joining and management operations"""

    def __init__(self, client):
        self.client = client

    async def join_channel(self, channel_link):
        """Join a channel with error handling"""
        try:
            # Extract channel identifier
            if 'joinchat' in channel_link or '/+' in channel_link:
                channel_id = channel_link.split('/')[-1].lstrip('+')
                is_private = True
            else:
                channel_id = channel_link.split('/')[-1]
                is_private = False

            # Check if already joined by trying to get channel info
            try:
                if is_private:
                    # For private channels, we can't easily check without joining
                    await self.client(ImportChatInviteRequest(channel_id))
                else:
                    # For public channels, check if we're already a member
                    channel = await self.client.get_entity(channel_id)
                    if hasattr(channel, 'left') and channel.left:
                        await self.client(JoinChannelRequest(channel_id))
                    else:
                        logger.info(f"Already a member of {channel_link}")
                        return True
            except UserAlreadyParticipantError:
                logger.info(f"Already a member of {channel_link}")
                return True

            logger.info(f"Successfully joined channel: {channel_link}")
            return True
        except (ChannelPrivateError, InviteHashInvalidError, InviteHashExpiredError) as e:
            logger.error(f"Cannot join channel {channel_link}: {str(e)}")
            return False
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"FloodWaitError: Must wait {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error joining channel {channel_link}: {str(e)}")
            return False