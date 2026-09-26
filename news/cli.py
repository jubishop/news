"""Operator commands shared by local development and systemd."""

import json

import click
from flask import current_app

from .db import migrate, transaction
from . import backups, incidents
from .maintenance import maintain


def register(app):
    @app.cli.command("init-db")
    def init_db():
        migrate(current_app.config["DATABASE"])
        click.echo("Database migrated.")

    @app.cli.command("maintain")
    def maintenance():
        result = maintain(current_app.config)
        from .notifications import deliver

        result["notifications"] = deliver(current_app.config)
        click.echo(json.dumps(result))

    def backup_command(operation, key):
        from .notifications import deliver

        try:
            result = operation(current_app.config)
        except Exception as error:
            with transaction(current_app.config["DATABASE"], write=True) as connection:
                incidents.observe(
                    connection,
                    key,
                    key.replace("-", "_"),
                    "News "
                    + key.replace("-", " ")
                    + " failed. Check the service and backup configuration. "
                    "Existing remote snapshots and the last successful measurement are retained.",
                )
            deliver(current_app.config)
            raise click.ClickException(
                key + " failed (" + type(error).__name__ + ")."
            ) from None
        with transaction(current_app.config["DATABASE"], write=True) as connection:
            incidents.resolve(connection, key)
        deliver(current_app.config)
        click.echo(json.dumps(result))

    @app.cli.command("backup")
    def backup():
        backup_command(backups.backup, "backup-failed")

    @app.cli.command("restore-check")
    def restore_check():
        backup_command(backups.restore_check, "restore-failed")


if __name__ == "__main__":
    from . import create_app

    app = create_app()
    with app.app_context():
        app.cli()
