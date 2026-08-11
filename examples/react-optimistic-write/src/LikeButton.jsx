import { useEffect, useState } from "react";

const faultMode =
  new URLSearchParams(window.location.search).get("fault") ??
  import.meta.env.VITE_DEMO_DEFAULT_FAULT ??
  null;

export function LikeButton() {
  const [liked, setLiked] = useState(false);
  const [phase, setPhase] = useState("loading");

  useEffect(() => {
    const controller = new AbortController();

    async function loadServerTruth() {
      try {
        const response = await fetch("/api/like", {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`GET /api/like returned ${response.status}`);
        }
        const state = await response.json();
        setLiked(state.liked);
        setPhase("ready");
      } catch (error) {
        if (error.name !== "AbortError") {
          setPhase("load-error");
        }
      }
    }

    loadServerTruth();
    return () => controller.abort();
  }, []);

  async function likeArticle() {
    const previousLiked = liked;
    setLiked(true);

    if (faultMode === "omit-post") {
      setPhase("omitted");
      return;
    }

    setPhase("saving");
    try {
      const response = await fetch("/api/like", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(faultMode === "reject-post"
            ? { "x-demo-fault": "reject" }
            : {}),
        },
        body: JSON.stringify({ liked: true }),
      });
      if (!response.ok) {
        throw new Error(`POST /api/like returned ${response.status}`);
      }
      setPhase("saved");
    } catch {
      setLiked(previousLiked);
      setPhase("write-error");
    }
  }

  const status = {
    loading: "Loading server truth…",
    ready: liked
      ? "Ready. The server says this article is liked."
      : "Ready. The server says this article is not liked.",
    saving: "Showing optimistic success while the write is pending…",
    saved: "Saved on server.",
    omitted: "Optimistic UI updated; POST omitted by demo fault.",
    "load-error": "Could not load server truth.",
    "write-error": "Ready after rollback.",
  }[phase];

  return (
    <section className="demo-card" aria-labelledby="demo-title">
      <div>
        <p className="card-label">Article reaction</p>
        <h2 id="demo-title">A tiny optimistic write</h2>
      </div>
      <button
        type="button"
        aria-pressed={liked}
        disabled={["loading", "saving", "load-error"].includes(phase)}
        onClick={likeArticle}
      >
        <span aria-hidden="true">♥</span>
        Like article
      </button>
      <p className="status" role="status">
        {status}
      </p>
      {phase === "write-error" ? (
        <p className="alert" role="alert">
          Write failed. Optimistic state rolled back.
        </p>
      ) : null}
    </section>
  );
}
