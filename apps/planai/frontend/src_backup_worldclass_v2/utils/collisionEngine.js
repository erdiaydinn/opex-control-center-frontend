export function rectOf(n) {
  return {
    x1: Number(n.x || 0),
    y1: Number(n.y || 0),
    x2: Number(n.x || 0) + Number(n.w || 0),
    y2: Number(n.y || 0) + Number(n.h || 0),
  };
}

export function rectsOverlap(a, b) {
  const A = rectOf(a);
  const B = rectOf(b);
  return A.x1 < B.x2 && A.x2 > B.x1 && A.y1 < B.y2 && A.y2 > B.y1;
}

export function minGapBetweenRects(a, b) {
  const A = rectOf(a);
  const B = rectOf(b);
  const dx = Math.max(B.x1 - A.x2, A.x1 - B.x2, 0);
  const dy = Math.max(B.y1 - A.y2, A.y1 - B.y2, 0);
  return Math.sqrt(dx * dx + dy * dy);
}
