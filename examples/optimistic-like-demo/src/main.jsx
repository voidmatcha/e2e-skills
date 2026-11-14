import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LikeButton } from "./LikeButton.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <main>
      <p className="demo-label">Demo app, not a real product</p>
      <LikeButton />
    </main>
  </StrictMode>,
);
