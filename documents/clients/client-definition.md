# MCP Client Requirements

**To use Chronos Health, your AI client needs three things:**

1. **A chat interface** — connected to a local or cloud-based AI model
2. **MCP support over HTTP** — the ability to connect to an MCP server endpoint and present its tools to the AI
3. **Custom system prompt** — the ability to inject a persona definition that shapes the AI's behavior and sets guardrails. 

If your client has all three, it can work with Chronos Health.

---

## Optional Features

These aren't required but significantly improve the experience:

| Feature | Why It Matters |
|---------|---------------|
| **Multiple MCP servers** | Load the Librarian alongside a filesystem MCP server for coding workflows (Librarian+Coder persona) |
| **Intelligent context control** | LibraryManager mode exposes 18 tools. Models with good context management handle large tool sets more reliably |
| **System logs** | When MCP connections fail or tools behave unexpectedly, logs are essential for debugging |

---

## Tested Clients

Chronos Health has been tested with the following clients:

| Client                          | Type           | Multi-MCP | Best For                                                                                              |
| ------------------------------- | -------------- | --------- | ----------------------------------------------------------------------------------------------------- |
| [Jan.ai](./jan-client.md)               | Desktop app    | ✅ Yes     | General use — flexible, multiple MCP servers, good for all three personas                             |
| [LM Studio](./lmstudio-client.md)          | Desktop app    | ✅ Yes     | Local models — excellent context management for smaller models working with large tool sets           |
| [Kilocode CLI](./kilocode-cli-client.md) | CLI / dev tool | ✅ Yes     | Software development — Already has the persona of the coder-librarian defined by the agents built in. |

Each client has its own setup guide in this directory.

---

## Network Connection

The MCP interface uses standard HTTP transport. The client can connect to the server from:

| Location | Address | Notes |
|----------|---------|-------|
| Same machine | `http://localhost:8890/mcp` | Default — no network configuration needed |
| Local network | `http://server-ip:8890/mcp` | Use the server's LAN IP address |
| Remote (anywhere) | `http://100.x.y.z:8890/mcp` | Use the server's Tailscale IPv4 address |

For remote access, both devices must be members of the same Tailscale tailnet. See [Tailscale remote access](./tailscale-remote.md) for setup instructions.

---

## Choosing a Server Endpoint

Connect to the endpoint that matches your intended use:

| If You Want... | Connect To |
|----------------|------------|
| Search and read documents | `http://localhost:8890/mcp` (LibraryUser, 14 tools) |
| Manage libraries (create, sync, rebuild) | `http://localhost:8889/mcp` (LibraryManager, 18 tools) |
| Full system administration | `http://localhost:8891/mcp` (Admin, all tools) |

Smaller tool sets improve AI accuracy — connect to the mode with the fewest tools that meets your needs.
