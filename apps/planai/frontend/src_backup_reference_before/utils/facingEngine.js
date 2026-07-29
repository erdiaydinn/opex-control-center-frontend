
export function calculateFacingRecommendation(
  product,
  shelfWidthCm = 100
) {
  const width =
    Number(product.width_cm || product.product_width_in_cm || 1);

  const depth =
    Number(product.depth_cm || product.product_depth_in_cm || 1);

  const height =
    Number(product.height_cm || product.product_height_in_cm || 1);

  const dailySales =
    Number(
      product.daily_sales ||
      product.sales_per_day ||
      product.avg_daily_sales ||
      0
    );

  const refillSeconds =
    Number(product.refill_seconds || 95);

  const unitsPerFacing =
    Math.max(
      1,
      Math.floor(30 / Math.max(depth, 1))
    );

  const targetRefillPerDay = 3;

  const recommendedFacing =
    Math.max(
      1,
      Math.ceil(
        dailySales /
        (unitsPerFacing * targetRefillPerDay)
      )
    );

  const usedWidth =
    recommendedFacing * width;

  const fillRate =
    Math.min(
      100,
      (usedWidth / shelfWidthCm) * 100
    );

  const refillCount =
    dailySales /
    (unitsPerFacing * recommendedFacing);

  const refillLaborSeconds =
    refillCount * refillSeconds;

  const refillLaborMinutes =
    refillLaborSeconds / 60;

  let refillRisk = "LOW";

  if (refillCount > 8) {
    refillRisk = "HIGH";
  } else if (refillCount > 4) {
    refillRisk = "MEDIUM";
  }

  let density = "LOW";

  if (fillRate > 85) {
    density = "HIGH";
  } else if (fillRate > 60) {
    density = "MEDIUM";
  }

  let aiScore = 100;

  aiScore -= refillCount * 3;

  if (fillRate < 40) {
    aiScore -= 15;
  }

  if (fillRate > 95) {
    aiScore -= 10;
  }

  aiScore =
    Math.max(
      0,
      Math.min(100, Math.round(aiScore))
    );

  return {
    width,
    depth,
    height,

    dailySales,

    recommendedFacing,

    unitsPerFacing,

    fillRate:
      Number(fillRate.toFixed(1)),

    refillCount:
      Number(refillCount.toFixed(1)),

    refillLaborMinutes:
      Number(refillLaborMinutes.toFixed(1)),

    refillRisk,

    density,

    aiScore
  };
}
