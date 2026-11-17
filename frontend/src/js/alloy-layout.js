export function nearestPosition(ideal, size, obstacles, viewport, gap = 16) {
  const find = bounds => {
    const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
    const x = [ideal.x, ...obstacles.flatMap(rect => [rect.x - size.width - gap, rect.x + rect.width + gap])];
    const y = [ideal.y, ...obstacles.flatMap(rect => [rect.y - size.height - gap, rect.y + rect.height + gap])];
    const xs = new Set(x.map(value => clamp(value, bounds.left, bounds.right - size.width)));
    const ys = new Set(y.map(value => clamp(value, bounds.top, bounds.bottom - size.height)));
    let best, distance = Infinity;
    for (const candidateX of xs) for (const candidateY of ys) {
      const score = (candidateX - ideal.x) ** 2 + (candidateY - ideal.y) ** 2;
      if (score >= distance || obstacles.some(rect =>
        candidateX < rect.x + rect.width + gap && candidateX + size.width + gap > rect.x &&
        candidateY < rect.y + rect.height + gap && candidateY + size.height + gap > rect.y)) continue;
      best = {x: candidateX, y: candidateY};
      distance = score;
    }
    return best;
  };
  if (viewport.right - viewport.left >= size.width && viewport.bottom - viewport.top >= size.height) {
    const visible = find(viewport);
    if (visible) return visible;
  }
  return find({left: -Infinity, top: -Infinity, right: Infinity, bottom: Infinity});
}

export function wireSegment(a, b) {
  const curve = Math.max(25, Math.min(115, Math.abs(a.x - b.x) * .5));
  return `M ${a.x},${a.y} C ${a.x + curve},${a.y} ${b.x - curve},${b.y} ${b.x},${b.y}`;
}
