"""
Video processing and upload functions
"""
import asyncio
import logging
import os
import random

from config import ADDITIONAL_CHANNELS, TARGET_CHANNEL_ID

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles video downloading, processing, and uploading"""

    def __init__(self, client):
        self.client = client
        self.max_retries = 3
        # Bot usernames for link generation (from genlink.py)
        self.bot_usernames = ['@boltarhegabot', '@Dairy_share2bot', '@quality_filesbot', '@File_extractorbot', '@Flipkart_filebot', '@Kitkat_sharebot', '@Unfiltered_filebot', '@Desiiihub_bot', '@Sanzzyyyyyfree_bot']
        # Track original posts and their access links
        self.original_posts = {}
        # Additional channels for posting access links (loaded from config)
        self.additional_channels = ADDITIONAL_CHANNELS.copy()
        logger.info(f"Initialized with {len(self.additional_channels)} additional channels: {self.additional_channels}")

    async def forward_video(self, message, retry_count=0):
        """Forward video to target channel with error handling"""
        try:
            # Try to forward first, if it fails, use download and re-upload
            try:
                await self.client.send_file(TARGET_CHANNEL_ID, message)
                return True
            except Exception as e:
                logger.warning(f"Forward failed: {e}, using download and re-upload...")
                return await self.download_and_reupload_video(message)
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}")
            return False

    def add_additional_channel(self, channel_id):
        """Add an additional channel for posting access links"""
        if channel_id not in self.additional_channels:
            self.additional_channels.append(channel_id)
            logger.info(f"Added additional channel: {channel_id}")

    def track_original_post(self, original_message, uploaded_message_id, access_link):
        """Track original post and its corresponding access link"""
        original_key = f"{original_message.chat_id}_{original_message.id}"
        self.original_posts[original_key] = {
            'original_message': original_message,
            'uploaded_message_id': uploaded_message_id,
            'access_link': access_link,
            'timestamp': asyncio.get_event_loop().time()
        }
        logger.info(f"Tracked original post {original_key} -> access link: {access_link}")

    async def replace_original_link(self, original_message, access_link):
        """Replace the original bot link in the message with access link"""
        try:
            if not hasattr(original_message, 'text') or not original_message.text:
                return False

            # Find bot links in the original message
            import re
            bot_links = re.findall(r'https://t\.me/[a-zA-Z0-9_]+bot[^\s]*', original_message.text)

            if not bot_links:
                logger.warning("No bot links found in original message")
                return False

            # Replace the first bot link with access link
            new_text = original_message.text.replace(bot_links[0], access_link)

            # Edit the original message
            await self.client.edit_message(
                original_message.chat_id,
                original_message.id,
                new_text
            )

            logger.info(f"Successfully replaced bot link with access link in message {original_message.id}")
            return True

        except Exception as e:
            logger.error(f"Error replacing original link: {e}")
            return False

    async def post_to_additional_channels(self, access_link, video_info=None):
        """Post access link to additional channels"""
        for channel_id in self.additional_channels:
            try:
                post_text = f"🎬 **New Video Access Link**\n\n{access_link}"
                if video_info:
                    post_text += f"\n\n📹 **Video Info:** {video_info}"

                await self.client.send_message(channel_id, post_text)
                logger.info(f"Posted access link to additional channel {channel_id}")
                await asyncio.sleep(2)  # Avoid flood wait

            except Exception as e:
                logger.error(f"Error posting to channel {channel_id}: {e}")

    async def generate_access_link(self, message_id, is_batch=False, start_id=None, end_id=None):
        """Generate access link for uploaded video using genlink.py logic"""
        try:
            from helper_func import encode
            from info import FILE_STORE_CHANNEL

            if is_batch and start_id and end_id:
                # For batch links (multiple videos)
                string = f"get-{start_id * abs(int(FILE_STORE_CHANNEL[0]))}-{end_id * abs(int(FILE_STORE_CHANNEL[0]))}"
            else:
                # For single video links
                string = f"get-{message_id * abs(int(FILE_STORE_CHANNEL[0]))}"

            base64_string = encode(string)
            if not base64_string:
                logger.error("Failed to encode string for access link")
                return None

            bot_username = random.choice(self.bot_usernames).lstrip('@')
            link = f"https://t.me/{bot_username}?start={base64_string}"

            logger.info(f"Generated access link: {link}")
            return link

        except Exception as e:
            logger.error(f"Error generating access link: {str(e)}")
            return None

    async def download_and_reupload_video(self, message, original_message=None):
        """Download video and re-upload to target channel preserving original format"""
        try:
            logger.info("Downloading video for re-upload...")
            # Download the video with original attributes
            video_path = await message.download_media()
            if video_path:
                logger.info(f"Downloaded video to: {video_path}")

                # Prepare upload attributes to preserve original video properties
                upload_kwargs = {}

                # Copy video attributes if available
                if hasattr(message, 'video') and message.video:
                    video = message.video
                    if hasattr(video, 'duration'):
                        upload_kwargs['duration'] = video.duration
                    if hasattr(video, 'width') and hasattr(video, 'height'):
                        upload_kwargs['width'] = video.width
                        upload_kwargs['height'] = video.height
                    if hasattr(video, 'supports_streaming'):
                        upload_kwargs['supports_streaming'] = video.supports_streaming

                # Use original caption if available, otherwise no caption
                caption = getattr(message, 'text', None) or getattr(message, 'caption', None) or ""

                # Upload to target channel preserving original format
                uploaded_message = await self.client.send_file(
                    TARGET_CHANNEL_ID,
                    video_path,
                    caption=caption,
                    **upload_kwargs
                )
                logger.info("Successfully re-uploaded video to target channel preserving original format")

                # Generate access link for single video
                access_link = await self.generate_access_link(uploaded_message.id, is_batch=False)
                if access_link:
                    logger.info(f"Generated access link: {access_link}")

                    # Track the original post and access link if original message is provided
                    if original_message:
                        self.track_original_post(original_message, uploaded_message.id, access_link)

                        # Replace original bot link with access link
                        await self.replace_original_link(original_message, access_link)

                        # Post to additional channels
                        video_info = f"Duration: {upload_kwargs.get('duration', 'Unknown')}" if 'duration' in upload_kwargs else None
                        await self.post_to_additional_channels(access_link, video_info)

                # Clean up downloaded file
                try:
                    os.remove(video_path)
                    logger.info("Cleaned up downloaded video file")
                except Exception as e:
                    logger.warning(f"Could not clean up file: {e}")
                return uploaded_message.id
            else:
                logger.error("Failed to download video")
                return False
        except Exception as e:
            logger.error(f"Error in download and re-upload: {str(e)}")
            return False

    async def process_videos_with_batch_links(self, messages, original_message=None):
        """Process multiple videos and generate batch access link"""
        try:
            if not messages:
                logger.warning("No messages provided for batch processing")
                return None

            uploaded_message_ids = []

            # Upload all videos first
            for message in messages:
                if hasattr(message, 'video') and message.video:
                    uploaded_id = await self.download_and_reupload_video(message, original_message)
                    if uploaded_id:
                        uploaded_message_ids.append(uploaded_id)

            if len(uploaded_message_ids) >= 2:
                # Generate batch access link
                start_id = min(uploaded_message_ids)
                end_id = max(uploaded_message_ids)

                access_link = await self.generate_access_link(
                    start_id,
                    is_batch=True,
                    start_id=start_id,
                    end_id=end_id
                )

                if access_link:
                    logger.info(f"Generated batch access link: {access_link}")

                    # Track the original post and batch access link if original message is provided
                    if original_message:
                        self.track_original_post(original_message, f"{start_id}_{end_id}", access_link)

                        # Replace original bot link with batch access link
                        await self.replace_original_link(original_message, access_link)

                        # Post to additional channels
                        await self.post_to_additional_channels(access_link, f"Batch of {len(uploaded_message_ids)} videos")

                    return access_link

            elif len(uploaded_message_ids) == 1:
                # Single video, generate single access link
                access_link = await self.generate_access_link(uploaded_message_ids[0], is_batch=False)
                if access_link and original_message:
                    self.track_original_post(original_message, uploaded_message_ids[0], access_link)
                    await self.replace_original_link(original_message, access_link)
                    await self.post_to_additional_channels(access_link, "Single video")

                return access_link

            return None

        except Exception as e:
            logger.error(f"Error in batch video processing: {str(e)}")
            return None