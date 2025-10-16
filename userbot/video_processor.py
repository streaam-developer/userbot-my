"""
Video processing and upload functions
"""
import logging
import os

from config import TARGET_CHANNEL_ID

logger = logging.getLogger(__name__)

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
                await self.client.send_file(
                    TARGET_CHANNEL_ID,
                    video_path,
                    caption=caption,
                    **upload_kwargs
                )
                logger.info("Successfully re-uploaded video to target channel preserving original format")

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