import tempfile
import unittest
from pathlib import Path

from app.services.video_service import VideoService


class VideoServiceHardeningTests(unittest.TestCase):
    def test_nonempty_corrupt_media_fails_without_fabricated_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.mp4"
            path.write_bytes(b"not a video" * 100)
            with self.assertRaisesRegex(ValueError, "cannot be decoded|no decodable|invalid"):
                VideoService.inspect_video(str(path))


if __name__ == "__main__":
    unittest.main()
