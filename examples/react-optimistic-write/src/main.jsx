import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { LikeButton } from "./LikeButton.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <main className="app-shell">
      <p className="eyebrow">Executable E2E example</p>
      <h1>Optimistic pixels are not persisted truth.</h1>
      <p className="intro">
        The button updates immediately. A trustworthy test also proves the
        write happened and survives a reload.
      </p>
      <LikeButton />
    </main>
  </StrictMode>,
);
