# Security Considerations

## Known Risks

### Command Injection via Context Commands (by design)

The context command system (`twag/web/routes/context.py`) executes user-defined shell commands with tweet-derived variable substitution. While variables are shell-escaped via `shlex.quote()`, the command templates themselves are stored and executed as arbitrary shell commands. This is by design for extensibility, but means **anyone with write access to the context commands API can execute arbitrary commands** on the host.

**Mitigation:** The web API currently has no authentication. If exposed beyond localhost, add authentication middleware before the context command routes, or restrict context command creation to the CLI.

### No Authentication on Web API

The FastAPI web server (`twag/web/app.py`) has no authentication or authorization. CORS is restricted to localhost origins, and the default bind address is `127.0.0.1`, but these are not substitutes for proper auth if the server is exposed to a network.

**Mitigation:** Do not bind to `0.0.0.0` or expose the server without adding authentication. If network access is needed, place the server behind a reverse proxy with authentication.
