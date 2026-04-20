# Tailscale Remote Access

See the tailscale documentation about setting up the tailnet. If the librarian MCP server and the client device are members of the same tailnet one can substitute localhost with the ip4 tailscale address in the json config for mcp in the client and you will be able to access your libraries from anywhere over a secure vpn.

The mcp server must be co-located with the libraries on the same pc. The clients may be remote from the mcp server and the libraries using the tailscale vpn.
