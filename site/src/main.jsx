import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { applyTheme, getInitialTheme } from "./lib/theme.js";
import "./index.css";

// Apply the theme before first paint so there's no light-mode flash.
applyTheme(getInitialTheme());

createRoot(document.getElementById("root")).render(
    <StrictMode>
        <App />
    </StrictMode>
);
