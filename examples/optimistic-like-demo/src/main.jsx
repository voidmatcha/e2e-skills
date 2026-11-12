import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LikeButton } from "./LikeButton.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <main>
      <h1>Demo feed</h1>
      <LikeButton />
    </main>
  </StrictMode>,
);
