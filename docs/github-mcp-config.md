# GitHub MCP Server Configuration

The agent supports two search backends:

| Backend | Setting | Description |
|---------|---------|-------------|
| REST API | `GITHUB_SEARCH_BACKEND=api` | Default. Stable, no extra deps. |
| MCP Server | `GITHUB_SEARCH_BACKEND=mcp` | Richer results via GitHub GraphQL. |
| Auto | `GITHUB_SEARCH_BACKEND=auto` | Tries MCP first, falls back to REST. |

## Setup

### Docker (Recommended)
```bash
docker pull ghcr.io/github/github-mcp-server
```

### Build from Source (No Docker)
```bash
git clone https://github.com/github/github-mcp-server.git
cd github-mcp-server
go build -o github-mcp-server ./cmd/github-mcp-server
```

See `.env.example` for full configuration.
