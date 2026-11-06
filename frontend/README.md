# Frontend

The FastAPI server serves `index.html`, native JavaScript from `src/js/`, CSS from `src/styles/`, and static assets from `public/`. Start the server from the repository root using the [setup instructions](../README.md#run-locally). The frontend runs directly in the browser with no build step.

`shell.js` switches screens and persists appearance preferences. `rutile-scene.js` handles camera motion, the Canvas lattice, and the fallback gem drawing. `gem-models.js` defines the faceted geometry, and `gem-optics.js` renders the two specimens with WebGL 2. `app.js` handles the phase-diagram workspace and its API requests. See the [interface guide](../docs/ui-ux.md) for screen behavior and font sources.
