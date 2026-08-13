import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

// Deliberately not wrapped in React.StrictMode.
//
// StrictMode double-invokes effects in development: mount, clean up, mount again. That
// means building a WebGL context and its worker pool, tearing them down and building them
// again on every page load, which is wasteful for an external resource this heavy and is a
// well-known source of subtle MapLibre lifecycle bugs.
//
// To be accurate about what this did and did not fix: it was suspected of causing a blank
// map during development and did not. The cause was traced elsewhere, and is recorded in
// docs/STATUS.md. Removing it remains defensible on its own merits.
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
