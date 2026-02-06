"""Web server command."""

from pathlib import Path

import rich_click as click

from ._console import console


@click.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=5173, help="Port to bind to")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on code changes")
@click.option("--dev", is_flag=True, default=False, help="Dev mode: start Vite + FastAPI with HMR")
def web(host: str, port: int, reload: bool, dev: bool):
    """Start the web interface server."""
    import os
    import signal
    import subprocess
    import sys

    project_dir = Path(__file__).parent.parent.parent
    frontend_dir = Path(__file__).parent.parent / "web" / "frontend"

    if dev:
        # Dev mode: start both Vite dev server and FastAPI (API-only)
        if not (frontend_dir / "node_modules").exists():
            console.print("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)

        console.print("Starting dev servers:")
        console.print(f"  Vite (frontend):  http://{host}:8080")
        console.print(f"  FastAPI (API):    http://{host}:{port}")
        console.print(f"Open http://{host}:8080 for hot reload")
        console.print("Press Ctrl+C to stop both")

        env = {**os.environ, "TWAG_DEV": "1"}

        uvicorn_cmd = [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "--with",
            "uvicorn[standard]",
            "uvicorn",
            "twag.web:create_app",
            "--host",
            host,
            "--port",
            str(port),
            "--factory",
        ]
        if reload:
            uvicorn_cmd.append("--reload")

        vite_cmd = ["npm", "run", "dev"]

        procs = []
        try:
            procs.append(subprocess.Popen(uvicorn_cmd, env=env))
            procs.append(subprocess.Popen(vite_cmd, cwd=frontend_dir))

            # Wait for either to exit
            while all(p.poll() is None for p in procs):
                try:
                    procs[0].wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            for p in procs:
                p.send_signal(signal.SIGTERM)
            for p in procs:
                p.wait(timeout=5)
    else:
        console.print(f"Starting twag web interface at http://{host}:{port}")
        console.print("Press Ctrl+C to stop")

        cmd = [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "--with",
            "uvicorn[standard]",
            "uvicorn",
            "twag.web:create_app",
            "--host",
            host,
            "--port",
            str(port),
            "--factory",
        ]
        if reload:
            cmd.append("--reload")

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            console.print(
                "[red]Error: 'uv' not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh[/red]"
            )
            sys.exit(1)
        except KeyboardInterrupt:
            pass
