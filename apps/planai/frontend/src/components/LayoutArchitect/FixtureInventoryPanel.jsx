import React from "react";
import { FIXTURE_CATALOG } from "../../data/fixtureCatalog";

const TYPES = Object.keys(FIXTURE_CATALOG);
export default function FixtureInventoryPanel({ inventory = {}, onChange }) {
  function setCount(type, count) { onChange?.({ ...inventory, [type]: Math.max(0, Number(count || 0)) }); }
  return <section className="fixture-inventory-panel"><h3>Fixture Envanteri</h3>{TYPES.map((type) => <label key={type}><span>{FIXTURE_CATALOG[type].label}</span><input type="number" min="0" value={inventory[type] || 0} onChange={(e) => setCount(type, e.target.value)} /></label>)}</section>;
}
