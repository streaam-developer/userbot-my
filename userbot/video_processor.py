"""
Video processing and upload functions with optimized download/upload
"""
import base64
import logging
import os
import asyncio
import aiofiles
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

from config import FILE_STORE_CHANNEL, TARGET_CHANNEL_ID

logger = logging.getLogger(__name__)

# Create a thread pool for CPU-intensive operations
thread_pool = ThreadPoolExecutor(max_workers=4)

async def encode(string: str) -> str:
    return base64.urlsafe_b64encode(string.encode()).decode().rstrip("=")

class VideoProcessor:
    """Handles video downloading, processing, and uploading"""

    def __init__(self, client, db_manager=None):
        self.client = client
        self.db_manager = db_manager
        self.ytdl_opts = {
            'format': 'best',
            'noplaylist': True,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': '%(id)s.%(ext)s'
        }

    async def _run_in_threadpool(self, func, *args):
        """Run CPU-intensive tasks in thread pool"""
        return await asyncio.get_event_loop().run_in_executor(thread_pool, func, *args)

    async def _download_with_ytdl(self, url):
        """Download video using yt-dlp in thread pool"""
        with yt_dlp.YoutubeDL(self.ytdl_opts) as ytdl:
            try:
                return await self._run_in_threadpool(ytdl.extract_info, url, download=True)
            except Exception as e:
                logger.error(f"YT-DLP download error: {str(e)}")
                return None

    async def forward_video(self, message, original_link=None):
        """Forward video to target channel with error handling and DB tracking"""
        try:
            # Check if link was already processed
            if original_link and self.db_manager:
                existing = await self.db_manager.get_processed_link(original_link)
                if existing:
                    logger.info(f"Link already processed: {original_link} -> {existing['new_link']}")
                    return existing['new_link']
            
            return await self.download_and_reupload_video(message, original_link)
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}")
            return False

    async def download_and_reupload_video(self, message, original_link=None):
        """Download video and re-upload with optimized methods"""
        try:
            logger.info("Downloading video for re-upload...")
            video_path = None
            
            # Use faster download method for media
            if hasattr(message, 'media'):
                # Use parallel chunks download for large files
                video_path = await message.download_media(progress_callback=self._download_progress)
            elif hasattr(message, 'text') and ('youtube.com' in message.text or 'youtu.be' in message.text):
                # Use yt-dlp for YouTube links
                info = await self._download_with_ytdl(message.text)
                if info:
                    video_path = f"{info['id']}.{info['ext']}"
            
            if video_path:
                logger.info(f"Downloaded video to: {video_path}")
                # Prepare optimized upload attributes
                upload_kwargs = {
                    'part_size_kb': 512,  # Optimize chunk size
                    'progress_callback': self._upload_progress
                }

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

                # Add video attributes if available
                if hasattr(message, 'video') and message.video:
                    video = message.video
                    upload_kwargs.update({
                        'duration': getattr(video, 'duration', None),
                        'width': getattr(video, 'width', None),
                        'height': getattr(video, 'height', None),
                        'thumb': await self._extract_thumbnail(message) if hasattr(video, 'thumbs') else None,
                        'supports_streaming': True
                    })

                # Use original caption
                caption = getattr(message, 'text', None) or getattr(message, 'caption', None) or ""

                # Upload with optimized settings
                uploaded_message = await self.client.send_file(
                    TARGET_CHANNEL_ID,
                    video_path,
                    caption=caption,
                    **upload_kwargs
                )
                logger.info("Successfully re-uploaded video to target channel")

                # Generate access link
                f_msg_id = uploaded_message.id
                s_msg_id = f_msg_id
                string = f"get-{s_msg_id * abs(FILE_STORE_CHANNEL[0])}"
                base64_string = await encode(string)
                new_link = f"https://t.me/boltarhegabot?start={base64_string}"

                # Store in database if enabled
                if self.db_manager and original_link:
                    video_info = {
                        'file_id': f_msg_id,
                        'duration': upload_kwargs.get('duration'),
                        'size': os.path.getsize(video_path) if os.path.exists(video_path) else None
                    }
                    await self.db_manager.add_processed_link(original_link, new_link, video_info)
                
                # Return the new link
                return new_link
            else:
                logger.error("Failed to download video")
                return None

        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            return None
        finally:
            # Clean up downloaded file
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    logger.info(f"Cleaned up temporary file: {video_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {video_path}: {str(e)}")

    async def _download_progress(self, current, total):
        """Track download progress"""
        if total:
            percentage = current * 100 / total
            if percentage % 10 == 0:  # Log every 10%
                logger.info(f"Download progress: {percentage:.1f}%")

    async def _upload_progress(self, current, total):
        """Track upload progress"""
        if total:
            percentage = current * 100 / total
            if percentage % 10 == 0:  # Log every 10%
                logger.info(f"Upload progress: {percentage:.1f}%")

    async def _extract_thumbnail(self, message):
        """Extract video thumbnail if available"""
        try:
            if hasattr(message.video, 'thumbs'):
                thumb = message.video.thumbs[0]
                return await message.download_media(thumb)
        except Exception as e:
            logger.error(f"Error extracting thumbnail: {str(e)}")
        return None
                try:
                    os.remove(video_path)
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