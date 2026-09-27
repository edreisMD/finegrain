"use client";

import { useEffect, useRef } from 'react';

// Independent signals gradually move into a shared rhythm.
// Motion ends after 4.5 seconds and respects reduced-motion preferences.
export default function GrainField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let start = 0;
    let time = motion.matches ? 4.5 : 0;
    const draw = () => {
      const width = canvas.getBoundingClientRect().width;
      const height = canvas.getBoundingClientRect().height;
      if (!width || !height) return;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.clearRect(0, 0, width, height);
      const columns = 55, rows = 9;
      const gap = width < 450 ? 2 : 3;
      const cellWidth = (width - gap * (columns - 1)) / columns;
      const cellHeight = (height - gap * (rows - 1)) / rows;
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < columns; x++) {
          const wave = Math.sin(x * 0.17 + y * 0.55 - time * 0.35);
          const ripple = Math.cos(x * 0.31 - y * 0.62 + time * 0.22);
          const glow = Math.max(0, Math.min(1, 0.45 + wave * 0.32 + ripple * 0.19));
          const low = [24, 42, 68], high = [126, 168, 236];
          const rgb = low.map((value, i) => Math.round(value + (high[i] - value) * glow));
          context.fillStyle = `rgb(${rgb.join(',')})`;
          context.beginPath();
          context.roundRect(x * (cellWidth + gap), y * (cellHeight + gap), cellWidth, cellHeight, Math.min(2, cellWidth / 3));
          context.fill();
        }
      }
    };
    const animate = (timestamp: number) => {
      if (!start) start = timestamp;
      time = Math.min((timestamp - start) / 1000, 4.5);
      draw();
      if (time < 4.5 && !motion.matches) frame = requestAnimationFrame(animate);
    };
    const stopMotion = () => {
      if (motion.matches) { cancelAnimationFrame(frame); time = 4.5; draw(); }
    };
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    motion.addEventListener('change', stopMotion);
    draw();
    if (!motion.matches) frame = requestAnimationFrame(animate);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); motion.removeEventListener('change', stopMotion); };
  }, []);
  return <div className="grain-art" aria-hidden="true"><canvas ref={canvasRef} /></div>;
}
