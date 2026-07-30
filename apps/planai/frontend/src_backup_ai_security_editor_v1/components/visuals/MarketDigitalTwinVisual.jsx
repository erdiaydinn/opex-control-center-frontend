import React from "react";
import "./MarketDigitalTwinVisual.css";

const racks = [
  { id: "A", x: 18, y: 19, h: 34, c: "ambient" },
  { id: "B", x: 34, y: 18, h: 37, c: "ambient" },
  { id: "C", x: 50, y: 20, h: 35, c: "ambient" },
  { id: "D", x: 20, y: 48, h: 30, c: "ambient" },
  { id: "E", x: 39, y: 48, h: 30, c: "ambient" },
  { id: "F", x: 58, y: 46, h: 32, c: "ambient" },
];

function Rack({ r }) {
  return (
    <div className={`mtv-rack ${r.c}`} style={{ left: `${r.x}%`, top: `${r.y}%`, height: `${r.h}%` }}>
      <span>{r.id}</span>
      {Array.from({ length: 5 }).map((_, i) => (
        <i key={i}>{Array.from({ length: 9 }).map((_, j) => <b key={j} />)}</i>
      ))}
    </div>
  );
}

function Cooler({ x, y, label, type }) {
  return (
    <div className={`mtv-cooler ${type}`} style={{ left: `${x}%`, top: `${y}%` }}>
      <em>{label}</em>
      <i /><i /><i /><i />
    </div>
  );
}

function Pallet({ x, y }) {
  return <div className="mtv-pallet" style={{ left: `${x}%`, top: `${y}%` }}>{Array.from({ length: 8 }).map((_, i)=><i key={i}/>)}</div>;
}

export default function MarketDigitalTwinVisual({ variant = "hero" }) {
  return (
    <div className={`mtv-shell ${variant}`}>
      <div className="mtv-stage">
        <div className="mtv-floor">
          <div className="mtv-outline" />
          <div className="mtv-wall mtv-wall-top" />
          <div className="mtv-wall mtv-wall-left" />
          <div className="mtv-door mtv-receiving">RECEIVING</div>
          <div className="mtv-door mtv-exit">EXIT</div>

          {racks.map((r) => <Rack key={r.id} r={r} />)}
          <Cooler x={73} y={15} label="+4" type="chilled" />
          <Cooler x={77} y={38} label="-18" type="frozen" />
          <Cooler x={70} y={61} label="ALGIDA" type="ice" />
          <Pallet x={19} y={77} />
          <Pallet x={48} y={76} />

          <div className="mtv-dispatch">DISPATCH</div>
          <div className="mtv-transpallet"><span/><b/></div>
          <div className="mtv-picker mtv-p1"><i/></div>
          <div className="mtv-picker mtv-p2"><i/></div>

          <svg className="mtv-route" viewBox="0 0 100 100" preserveAspectRatio="none">
            <path d="M9,76 C17,62 24,54 34,54 C43,54 42,37 52,37 C68,37 70,55 83,45 C88,41 90,70 82,78" />
          </svg>

          <div className="mtv-badge mtv-ambient">AMBIENT <b>82%</b></div>
          <div className="mtv-badge mtv-chilled">CHILLED +4 <b>74%</b></div>
          <div className="mtv-badge mtv-frozen">FROZEN -18 <b>68%</b></div>
        </div>
      </div>
    </div>
  );
}
