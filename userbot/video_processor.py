"""
Video processing and upload functions
"""
import aiofiles
import asyncio
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
            # Download the video with original attributes using aiofiles for better performance
            video_path = await message.download_media()
            if video_path:
                logger.info(f"Downloaded video to: {video_path}")

                # Prepare upload attributes to preserve original video properties
                upload_kwargs = {}

                # Copy video attributes if available and log them
                if hasattr(message, 'video') and message.video:
                    video = message.video
                    logger.info(f"Video attributes - Duration: {getattr(video, 'duration', 'N/A')}, "
                              f"Width: {getattr(video, 'width', 'N/A')}, Height: {getattr(video, 'height', 'N/A')}, "
                              f"Size: {getattr(video, 'size', 'N/A')}, Supports streaming: {getattr(video, 'supports_streaming', 'N/A')}")

                    if hasattr(video, 'duration') and video.duration is not None:
                        upload_kwargs['duration'] = video.duration
                    if hasattr(video, 'width') and video.width is not None and hasattr(video, 'height') and video.height is not None:
                        upload_kwargs['width'] = video.width
                        upload_kwargs['height'] = video.height
                    if hasattr(video, 'supports_streaming') and video.supports_streaming is not None:
                        upload_kwargs['supports_streaming'] = video.supports_streaming

                # Use original caption if available, otherwise no caption
                caption = getattr(message, 'text', None) or getattr(message, 'caption', None) or ""

                # Upload to target channel preserving original format with optimized send_file
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

                # Clean up downloaded file asynchronously
                try:
                    await asyncio.get_event_loop().run_in_executor(None, os.remove, video_path)
                    logger.info("Cleaned up downloaded video file")
                except Exception as e:
                    logger.warning(f"Could not clean up file: {e}")
                return link
            else:
                logger.error("Failed to download video")
                return False
        except Exception as e:
            logger.error(f"Error in download and re-upload: {str(e)}")
            return False
