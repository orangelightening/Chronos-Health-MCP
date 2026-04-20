# Jan.ai

JAN is a chat model hosting system with mcp client links.

## Installation

Goto Jan.ai and install JAN for your particular OS. 

## Configuration

1) Select a model from the many hosting services available. The model must be tool capable and intelligent enough to play the role of the chronos health librarian. More powerful ai's will have more capability then 4b or 9b models.
2)  Goto settings/mcp servers and add the librarian mcp. Using the http address for the librarian mcp server fill in either the form config or directly install the json described in the INSTALLATION.md document in this repo. If the chronos health mcp server is running and selected the active light will be lit. Since there are 3 endpoints available in the chronos health mcp server you can instantiate each endpoint as a separate mcp. In addition you may wish to set the  "Allow All MCP Tool Permissions" to true (if you don't you will be prompted for each tool you use) and turn on any other mcp servers you wish to use. 
3) Goto settings/assistants and add a new assistant. Name the assistant as you wish and then install one of the system_prompts from this repo or make up one of your own. The medical_specialist_system_prompt in this repo has a nice mix of guardrails and controlled use of the library plus native training data. The idea is to turn the ai into the type of assistant you need.
4) Goto New Projects and give the project a meaningful name and fill in the name of the assistant you defined in step 3 above.
5) click on the project name in the left hand window and you will be in a chat window with the ai you have chosen. It will have had the system_prompt from the assistant definition injected into its context and will have the chronos health mcp tools listed by hovering over the tool icon.

## Operation

 At this point you may begin a chat dialogue with the chronos health librarian. Be aware of context size limitations and switch to a new chat window to get back to clean context. Select a new chat window by clicking on the project name. If you wish to carry context into a new chat window you can have the ai summarise context in the old chat window and than load a context summary file into the new chat window. Have fun.
