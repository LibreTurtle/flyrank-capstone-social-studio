import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import repositories
from content import extract_article, title_from_markdown
from database import initialize_database
from services import ingest_markdown


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.setting = patch.dict(
            os.environ,
            {"SOCIAL_STUDIO_DATABASE": str(Path(self.temp_dir.name) / "posts.sqlite3")},
        )
        self.setting.start()
        initialize_database()

    def tearDown(self):
        self.setting.stop()
        self.temp_dir.cleanup()

    def test_markdown_post_is_stored_with_its_heading(self):
        post = ingest_markdown("## Project notes\n\nUseful source text.")
        stored = repositories.get_post(post["id"])

        self.assertEqual(post["title"], "Project notes")
        self.assertEqual(stored["body"], "## Project notes\n\nUseful source text.")
        self.assertEqual(stored["source_type"], "markdown")

    def test_article_page_title_and_readable_body_are_extracted(self):
        title, body = extract_article(
            "<html><head><title>Notes</title></head><body>"
            "<script>skip this</script><h1>Heading</h1><p>Useful text.</p></body></html>"
        )

        self.assertEqual(title, "Notes")
        self.assertIn("Useful text.", body)
        self.assertNotIn("skip this", body)

    def test_markdown_without_heading_uses_default_title(self):
        self.assertEqual(title_from_markdown("Body only"), "Untitled article")
