// Application context for static review; no fixture execution is requested.
export function startPreview(canvas: HTMLCanvasElement, progress: HTMLElement) {
  const context = canvas.getContext('2d');
  let tick = 0;
  function frame() {
    if (context) {
      context.fillStyle = '#2288cc';
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
    tick += 1;
    progress.textContent = String(tick);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
