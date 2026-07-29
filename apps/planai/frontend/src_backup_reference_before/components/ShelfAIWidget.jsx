
import React from "react";
import { calculateFacingRecommendation } from "../utils/facingEngine";
import "../styles/refill-ai.css";

export default function ShelfAIWidget({
  product,
  shelf
}) {
  const ai =
    calculateFacingRecommendation(
      product,
      shelf?.width_cm || 100
    );

  return (
    <div
      className={`
        shelf-card
        risk-${ai.refillRisk.toLowerCase()}
      `}
    >
      <div className="shelf-ai-wrapper">

        <div className="shelf-ai-top">

          <div className="shelf-fill">
            Fill {Math.round(ai.fillRate)}%
          </div>

          <div
            className={`shelf-risk ${ai.refillRisk.toLowerCase()}`}
          >
            {ai.refillRisk} REFILL
          </div>

        </div>

        <div className="shelf-ai-bottom">

          <span>
            {ai.recommendedFacing} facing
          </span>

          <span>
            {ai.refillCount}/day refill
          </span>

          <span>
            {ai.refillLaborMinutes}m labor
          </span>

          <span>
            AI {ai.aiScore}
          </span>

        </div>

      </div>
    </div>
  );
}
