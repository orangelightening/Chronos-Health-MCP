# Kilocode CLI

Kilocode-cli is an ide which hosts an AI and mcp interfaces. It operates as a chat window inside the cli terminal.

## Installation

Goto  https://kilo.ai/docs/getting-started/installing and download and install for your particular OS. 

## Configuration

1) Select a model from the many hosting services available. The model must be tool capable and intelligent enough to play the role of the chronos health librarian. More powerful ai's will have more capability then 4b or 9b models.
2) Referring to the kilocode-cli documentation install the chronos health mcp.
3)  This client is an **exception**  because it is primarily used as an ide for software development and comes equipped with agents. Each agent has its own persona. I leave it to the reader to define a new agent modelled after the system prompts in this repo or one of your own design. Because it is an ide it is instantiated in the project directory which may or may not be a library in the chronos health system. 

## Operation

 At this point you may begin a chat dialogue with the kilocode AI. It has whatever tool set you allocated depending on the endpoint selected in the mcp definition.

## ⚠️ Risk of Unintended File Modification

Kilocode operates directly on the filesystem of whatever project directory it is pointed at. When working in **plan mode** the AI proposes changes without executing them. However, the transition from plan mode to coding mode can be triggered by a conversational response that the AI interprets as permission to execute — even if that was not your intent.

Specifically: if the AI presents a plan and asks whether to proceed in a new context or the existing one, responding to that question can be treated as consent to switch to coding mode and begin executing immediately — with no further permission prompts for individual file operations.

**Mitigations:**

- Always point Kilocode at a directory you have backed up.
- Be cautious with any response that could be interpreted as approval to execute.
- If you would like to discuss a plan without risk of execution, use a client that does not have write access to your file system (such as Jan or LM Studio).

## Co-location

Kilocode-cli is by definition tied to the project window but may access local libraries or remote libraries using the method described in [Tailscale remote access](./tailscale-remote.md).
