"""Real Restic encryption, retention, and restore against local test storage."""

import io
import os
from pathlib import Path
import sqlite3
import subprocess
from unittest.mock import patch

from support import ServerFixture


class ResticIntegrationTests(ServerFixture):
    def test_backup_and_restore_use_real_restic(self):
        self.reporter()
        directory = Path(self.database).parent
        repository = directory / "repository"
        self.app.config["BACKUP_STATE"] = str(directory / "backup/size.json")
        process = subprocess.run
        environment = dict(
            os.environ,
            RESTIC_REPOSITORY=str(repository),
            RESTIC_PASSWORD="local-fixture-password",
            RESTIC_CACHE_DIR=str(directory / "cache"),
        )
        process(
            ["restic", "init", "--repository-version", "2"],
            env=environment,
            check=True,
            capture_output=True,
        )

        def local_storage(args, **kwargs):
            return process(args, env=environment, **kwargs)

        self.http.return_value = io.BytesIO(
            b"<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>"
        )
        self.http.side_effect = None
        with patch.dict(
            os.environ,
            RESTIC_REPOSITORY="s3:https://fixture.r2.cloudflarestorage.com/news",
            AWS_ACCESS_KEY_ID="fixture",
            AWS_SECRET_ACCESS_KEY="fixture",
        ):
            with patch("subprocess.run", side_effect=local_storage):
                runner = self.app.test_cli_runner()
                result = runner.invoke(args=["backup"])
                self.assertEqual(result.exit_code, 0, result.output)
                # Corrupt only the live fixture after backing up. Restore must read the snapshot.
                with sqlite3.connect(self.database) as connection:
                    connection.execute(
                        "UPDATE reporters SET prompt='Changed after backup'"
                    )
                result = runner.invoke(args=["restore-check"])
                self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(list((directory / "backup").glob("restore-*")))
        self.assertTrue((directory / "backup/restore.json").is_file())
