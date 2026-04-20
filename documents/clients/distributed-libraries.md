# Distributed Libraries with Syncthing and Tailscale

Libraries can be distributed across remote devices using Syncthing for file synchronization and Tailscale for secure network connectivity. The user edits documents on their own device. Syncthing maintains a mirror copy on the server. The MCP server operates on the mirror. Deliverables written by the MCP are synced back to the user's device automatically.

```
Remote device                Syncthing over Tailscale            Server
┌──────────────────┐         bidirectional, port 22000         ┌──────────────────┐
│ Obsidian vault   │  ◄──────── tcp://100.x.y.z:22000 ──────►  │ Mirror copy      │
│ Edit documents   │                                           │ Registered as    │
│ View deliverables│                                           │   MCP library    │
└──────────────────┘                                           └──────────────────┘
```

No code changes are required. The MCP server does not know or care that the library is a Syncthing mirror. It sees files on disk, which is exactly what it was designed for.

---

## Prerequisites

- **Syncthing** installed on both the remote device and the server
- **Tailscale** installed on both devices, both members of the same tailnet
- Both devices must be online for sync to occur

---

## Setup

### 1. Create the library on the server

Create the library directory on the server and register it as an MCP library. Use `add_library` from any MCP client connected to the Admin endpoint. This creates the `.librarian/` structure, a `delivery/` directory, and default `.librarianignore` and `.stignore` files automatically.

### 2. Note the Syncthing device IDs

On each machine, open the Syncthing web UI, go to **Actions → Show ID**, and copy the device ID. You now have the Syncthing IDs for both machines.

### 3. Add the remote device on the server

In the server's Syncthing web UI, add a remote device using the ID from step 2. Go to the **Advanced** tab and change the address from `dynamic` to `tcp://100.x.y.z:22000`, using the remote device's Tailscale IPv4 address.

### 4. Add the server device on the remote

In the remote's Syncthing web UI, add a device using the server's Syncthing ID. Go to the **Advanced** tab and change the address from `dynamic` to `tcp://100.x.y.z:22000`, using the server's Tailscale IPv4 address.

You now have two devices aware of each other over the Tailscale network.

### 5. Share the library from the server

In the server's Syncthing web UI, add a folder to sync. Point it at the library directory. In the **Sharing** tab, tick the box to share with the remote device. Go to the **Advanced** tab and set the direction to **Send Only**.

### 6. Accept the share on the remote

The remote device will receive an invitation to share a directory. Accept it and immediately edit the new folder share — change the folder path to where you want the library mirror to be created on the remote device (for example, `~/Sync/katherine-health`). Go to the **Advanced** tab and set the direction to **Receive Only**.

When you save, the remote directory will be created and Syncthing will copy the library from the server to the remote device.

### 7. Enable bidirectional sync

Once the initial sync is complete:

1. On the remote device, edit the shared folder, advanced tab and set the direction to **Send & Receive**.
2. On the server, edit the shared folder, advanced tab and set the direction to **Send & Receive**.

You now have two mirrored libraries.

---

## .stignore Configuration

The `.stignore` file controls what Syncthing does **not** sync between devices. The `add_library` command creates a default `.stignore` on the server that excludes `.librarian/`. This is essential — syncing ChromaDB would cause corruption.

**Server `.stignore`** (created automatically by `add_library`):
```
.librarian/
```

**Remote `.stignore`** — if the remote copy is being used as an Obsidian vault, create a `.stignore` file in the root of the remote directory with:
```
.obsidian/
.stignore
```

This keeps Obsidian configuration files from syncing back to the server.

---
## Ownership by the remote

This method creates a relatively safe method of limiting accidental damage to the data. You may adopt it or not as you see fit.
If this system is used it is important for the remote copy to assume ownership of the data. The method for doing this is to pause and un-pause the the synchronizing of the mirrors by going to the syncthing control panel on the remote side and selecting the folder and then hitting pause. The interface should be paused on the remote end unless the user wants to update the contents of the servers copy or wants to recieve a report. Pausing the folder sync allows the user to do complex editing on the remote copy and then sync the copies. Its a good safety feature. To reiterate. The folder should be paused for sync on the remote side except to sync editing changes with the server copy or to recieve a report from the server. Otherwise the safest state is to leave the remote folder paused.
## Workflow

The user's daily workflow is:
Assuming the folder syncthing interface is paused on the remote side.
1. **Edit** — Add, edit, or delete documents on the remote device using any tool (Obsidian, text editor, etc.)
2. Unpause the folder syncthing interface on the remote side. 
3. **Sync** — Syncthing detects changes and syncs them to the server mirror. This happens automatically when both devices are online. There may be a few seconds of latency.
4. When the folder show as sync'd pause the folder again.
5. **Index** — Run `sync_library_async` from any MCP client to re-index the changed files into ChromaDB, then check status to confirm completion.
6. **Query** — Ask the AI questions about the library contents. The AI searches the indexed mirror on the server side.
7. **Deliver**y — Request a report. The MCP writes it to the library's `delivery/` directory. 
8. Unpause the remote folder and Syncthing syncs it back to the remote device. Once sync'd the user pauses the folder sync  again. The user collects the document from their own vault.

---

## Deliverables

When the MCP writes a report using `write_document` with the library parameter, it writes to both the global sandbox and the library's `delivery/` directory. Syncthing syncs the delivery file to the remote device. The user finds it in their own vault without interacting with the server directly.

---

## Limitations

- **Both devices must be online** for sync to occur. If the remote device is offline, changes will not appear on the server until it reconnects.
- **Indexing is not automatic.** After Syncthing syncs new files to the mirror, `sync_library_async` must be run to update the ChromaDB index. A filesystem watcher to trigger automatic re-indexing is a planned enhancement.
- **Conflict files.** If the user edits a file locally while the MCP writes to the same file on the mirror, Syncthing will create a conflict copy. This is rare if the user only edits documents and the MCP only writes to the designated `delivery/` directory.
- **Latency.** Sync over cellular connections (hotspot) is noticeably slower than WiFi or wired. This is a Syncthing and network characteristic, not an MCP limitation.
- **macOS permissions.** On macOS, avoid using `~/Documents/` or `~/Desktop/` as the sync target — macOS restricts access to these directories. Use a custom directory like `~/Sync/` instead.

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Files not syncing | Both devices online? Syncthing running on both? Folder status shows "Up to Date"? |
| Old versions appearing | `.stignore` in place on server? Check for `.librarian` sync attempts |
| Port not connecting | Tailscale active on both? Can you ping the other device's Tailscale IP? Port 22000 not blocked? |
| MCP not seeing new files | Did you run `sync_library_async` after the sync completed? |
| Remote can't write to directory | macOS? Use `~/Sync/` instead of `~/Documents/`. Grant Full Disk Access to Syncthing in System Settings. |
