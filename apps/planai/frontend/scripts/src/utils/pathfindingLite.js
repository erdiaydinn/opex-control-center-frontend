export function estimateRouteDistance(nodes = []) {
  const pickNodes = nodes.filter((n) => n.kind === "module");
  if (!pickNodes.length) return 0;

  let dist = 0;
  let prev = { x: 0, y: 0 };
  for (const n of pickNodes) {
    dist += Math.abs(Number(n.x) - prev.x) + Math.abs(Number(n.y) - prev.y);
    prev = { x: Number(n.x), y: Number(n.y) };
  }
  return Math.round(dist * 50); // cm estimate
}
