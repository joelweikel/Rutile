# UI/UX direction

## Primary journey

Create/open a material project -> define composition -> choose a calculation -> review conditions and data suitability -> run -> inspect and compare results -> save/export.

## Initial workspaces

- **Materials/projects:** compositions, processing conditions, and saved calculations.
- **Data library:** source registration, validation status, coverage, and import details.
- **Phase diagrams:** calculation form, progress, plot, numerical results, and provenance.

Property modeling, heat treatments, and optimization can become additional workspaces as implemented.

## Interaction principles

Keep database file management out of the normal calculation workflow. Show a concise explanation of the selected source and any material limitations, with detailed provenance available on demand. An override is an advanced action, not a required step for every calculation.

Always label units and distinguish weight percent from atomic/mole percent. Validate composition totals and dependent-element behavior before submission. Use explicit loading, empty, partial-result, and error states. Support cancellation and protect unsaved inputs.

Use semantic HTML, keyboard-accessible controls, visible focus states, sufficient contrast, and plots whose meaning does not depend on color alone. Provide numerical tables and export options alongside diagrams. Build responsive layouts appropriate for dense desktop scientific workflows.

Begin with native JavaScript modules and shared CSS foundations. Keep API calls separate from view rendering. Mock data is acceptable for design prototypes only when clearly labeled as synthetic.
