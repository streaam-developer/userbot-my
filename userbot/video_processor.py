"""
Video processing and upload functions
"""
import base64
import logging
import os

from config import FILE_STORE_CHANNEL, TARGET_CHANNEL_ID

logger = logging.getLogger(__name__)

async def encode(string: str) -> str:
    return base64.urlsafe_b64encode(string.encode()).decode().rstrip("=")

class VideoProcessor:
    """Handles video downloading, processing, and uploading"""

    def __init__(self, client):
        self.client = client

    async def forward_video(self, message):
        """Forward video to target channel with error handling - always use download and re-upload to avoid forward tags"""
        try:
            # Always download and re-upload instead of forwarding to avoid forward tags
            return await self.download_and_reupload_video(message)
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}")
            return False

    async def download_and_reupload_video(self, message):
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

                # Generate and send access link
                f_msg_id = uploaded_message.id
                s_msg_id = f_msg_id  # For single video, f_msg_id and s_msg_id are the same
                string = f"get-{s_msg_id * abs(FILE_STORE_CHANNEL[0])}"
                base64_string = await encode(string)
                link = f"https://t.me/boltarhegabot?start={base64_string}"

                await self.client.send_message(TARGET_CHANNEL_ID, f"Access Link: {link}")
                logger.info(f"Successfully sent access link for video {f_msg_id}")


                # Clean up downloaded file
                try:
                    os.remove(video_path)
                    logger.info("Cleaned up downloaded video file")
                except Exception as e:
                    logger.warning(f"Could not clean up file: {e}")
                return True
            else:
                logger.error("Failed to download video")
                return False
        except Exception as e:
            logger.error(f"Error in download and re-upload: {str(e)}")
            return False

    async def process_video_for_link(self, message):
        """Process video and return access link without sending to target channel"""
        try:
            logger.info("Processing video for access link generation...")
            # Download the video
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
                logger.info("Successfully uploaded video to target channel for link generation")

                # Generate access link
                f_msg_id = uploaded_message.id
                s_msg_id = f_msg_id  # For single video, f_msg_id and s_msg_id are the same
                string = f"get-{s_msg_id * abs(FILE_STORE_CHANNEL[0])}"
                base64_string = await encode(string)
                link = f"https://t.me/boltarhegabot?start={base64_string}"

                logger.info(f"Generated access link for video {f_msg_id}: {link}")

                # Store the mapping for later retrieval
                # Note: This is a simple implementation. In production, you'd want to map the original bot link to this access link
                self.client._userbot.link_to_access_map['latest'] = link

                # Clean up downloaded file
                try:
                    os.remove(video_path)
                    logger.info("Cleaned up downloaded video file")
                except Exception as e:
                    logger.warning(f"Could not clean up file: {e}")

                return link
            else:
                logger.error("Failed to download video")
                return None
        except Exception as e:
            logger.error(f"Error in video processing for link: {str(e)}")
            return None