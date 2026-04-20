# LM Studio

LMstudio is a chat model hosting system with mcp client links.

## Installation

Goto  https://lmstudio.ai/download  and download and install for your particular OS. 

## Configuration

1) Select a model from the many hosting services available. The model must be tool capable and intelligent enough to play the role of the chronos health librarian. More powerful ai's will have more capability then 4b or 9b models.
2)  Goto the right pane and under integrations add the librarian mcp. Using the http address for the librarian mcp server end point directly edit  the json accessed under the "+ Install" button. The json is defined in the INSTALLATION.md document in this repo. If the chronos health mcp server is running and selected, the mcp name and the tools list will be shown in the right hand pane. Since there are 3 endpoints available in the chronos health mcp server you can instantiate each endpoint as a separate mcp. In the tools list you can turn on auto permission on each tool in the list. I usually allow all the read functionality but restrict anything major to ask permission.
3) Goto model settings in the right pane  and then install one of the system_prompts from this repo or make up one of your own. The medical_specialist_system_prompt in this repo has a nice mix of guardrails and controlled use of the library plus native training data. The idea is to turn the ai into the type of assistant you need.

## Operation

 At this point you may begin a chat dialogue with the chronos health librarian. Be aware of context size limitations and switch to a new chat window to get back to clean context. If you wish to carry context into a new chat window you can have the ai summarise context in the old chat window and than load a context summary file into the new chat window. LMstudio has good context/gpu management for small models doing big jobs.
