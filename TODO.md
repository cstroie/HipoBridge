# TODO

- [X] Introduce one shared "tab card" class (`.tab-card`) for the
  background/border/radius shared by `.analysis-card` (Imaging + Lab),
  `.report-card`, and `.ai-summary-card` — applied additively, no visual
  change. `.epi-card-inner` stays separate on purpose: it's an inner slot
  of `.epi-card` (which owns its own chrome), not a peer outer card like
  the other three.

- [X] Add a Copy button to the AI tab summary card, similar to the Copy button on the report tab.

- [X] Fix the card toolbar appearance inside epicrisis cards

- [X] After log in, check whoami to get the user's name and permissions.

- [X] Do not automatically generate the AI content after patient load.

- [X] Add support for "in progress" (performed, i think), and 'cancelled' exam status

- [X] Derive patient gender from CNP if not clearly specified 

- [X] Find a better color for the exams counter in Schedule

- [X] Remove the "Urgent" badge in lab and imaging and keep only the red border 

- [ ] Completr DICOM worklist round (query, select, execute, etc)

- [X] Free text seach in any epicrisis or reports to indentifi a (recent) patient

- [X] Propose a better model/template for Hipocrate 'Cereri' page

- [X] Fix the markdown submission format and conversion

- [ ] Switch the LLM profile (provider) from the frontend: add a selector in the
  User Account panel, keep the choice in browser local storage, and send it
  with each AI request so the server uses that `[provider:*]` from llm.cfg.

- [ ] Use the user's own local LLM (Ollama / LM Studio / llama.cpp on the client
  machine): let the browser call its localhost OpenAI-compatible endpoint
  directly (server-side calls cannot reach it), with the endpoint URL kept in
  browser local storage. Needs CORS enabled on the local server and a
  decision on whether prompts are built client-side or fetched from the server.
