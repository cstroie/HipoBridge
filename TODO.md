# TODO

- [ ] Introduce one shared "tab card body" class (e.g. `.tab-card-inner`) used by
  the report/epicrisis/lab/AI tabs instead of each tab inventing its own
  container name (`.epi-card-inner`, `.analysis-container`, `.ai-summary-card`,
  `.report-card`). Bigger refactor — normalize once all four are stable.

- [X] Add a Copy button to the AI tab summary card, similar to the Copy button on the report tab.

- [X] Fix the card toolbar appearance inside epicrisis cards

- [ ] After log in, check whoami to get the user's name and permissions.

- [X] Do not automatically generate the AI content after patient load.

- [X] Add support for "in progress" (perfomed, i think), and 'cancelled' exam status

- [X] Derive patient gender from CNP if not clearly specified 

- [X] Find a better color for the exams counter in Schedule

- [X] Remove the "Urgent" badge in lab and imaging and keep only the red border 

