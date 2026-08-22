export const PLANOGRAM_WALL_PASSAGE_CONTRACT = "eay.planogram.wall-passages.v1";
export const PLANOGRAM_WALL_PASSAGE_TYPES = Object.freeze(["door", "emergency_exit"]);

const PASSAGE_TYPES = new Set(PLANOGRAM_WALL_PASSAGE_TYPES);
const EPSILON = 1e-6;
const CENTERLINE_TOLERANCE_M = 0.03;
const ROTATION_TOLERANCE_DEG = 0.25;
const DEFAULT_WALL_HEIGHT_M = 2.7;
const DEFAULT_DOOR_HEIGHT_M = 2.1;
const MIN_SEGMENT_M = 0.02;

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rounded(value, precision = 4) {
  const factor = 10 ** precision;
  return Math.round(finite(value) * factor) / factor;
}

function text(value) {
  return String(value ?? "").trim();
}

function normalizedRotation(value) {
  let rotation = ((finite(value) % 360) + 360) % 360;
  if (rotation > 180) rotation -= 360;
  return rounded(rotation, 3);
}

function rotationDistance(left, right) {
  const delta = Math.abs(normalizedRotation(left) - normalizedRotation(right));
  return Math.min(delta, 360 - delta);
}

function axes(row) {
  const radians = finite(row?.rotationDeg) * Math.PI / 180;
  return {
    tangentX: Math.cos(radians),
    tangentY: Math.sin(radians),
    normalX: -Math.sin(radians),
    normalY: Math.cos(radians),
  };
}

function localToWorld(wall, alongM, normalM = 0) {
  const basis = axes(wall);
  return {
    centerXM: rounded(
      finite(wall.centerXM) + alongM * basis.tangentX + normalM * basis.normalX,
    ),
    centerYM: rounded(
      finite(wall.centerYM) + alongM * basis.tangentY + normalM * basis.normalY,
    ),
  };
}

function localOffset(wall, row) {
  const basis = axes(wall);
  const dx = finite(row?.centerXM) - finite(wall?.centerXM);
  const dy = finite(row?.centerYM) - finite(wall?.centerYM);
  return {
    alongM: dx * basis.tangentX + dy * basis.tangentY,
    normalM: dx * basis.normalX + dy * basis.normalY,
  };
}

function baseElement(row, overrides = {}) {
  return Object.freeze({
    ...row,
    ...overrides,
    coordinateAuthority: text(overrides.coordinateAuthority || row.coordinateAuthority || "preview"),
    productionReleaseAllowed: false,
  });
}

function passageValidation(wall, opening) {
  const offset = localOffset(wall, opening);
  const wallWidth = Math.max(0, finite(wall.widthM));
  const openingWidth = Math.max(0, finite(opening.widthM));
  const reasons = [];
  if (!wallWidth || !openingWidth || openingWidth >= wallWidth - EPSILON) {
    reasons.push("passage_width_invalid");
  }
  if (Math.abs(offset.normalM) > CENTERLINE_TOLERANCE_M) {
    reasons.push("passage_off_wall_centerline");
  }
  if (rotationDistance(wall.rotationDeg, opening.rotationDeg) > ROTATION_TOLERANCE_DEG) {
    reasons.push("passage_rotation_mismatch");
  }
  if (Math.abs(finite(wall.depthM) - finite(opening.depthM)) > CENTERLINE_TOLERANCE_M) {
    reasons.push("passage_depth_mismatch");
  }
  const startM = offset.alongM - openingWidth / 2;
  const endM = offset.alongM + openingWidth / 2;
  if (startM < -wallWidth / 2 - EPSILON || endM > wallWidth / 2 + EPSILON) {
    reasons.push("passage_outside_wall_span");
  }
  return Object.freeze({
    valid: reasons.length === 0,
    openingId: text(opening.id),
    wallId: text(wall.id),
    startM: rounded(startM),
    endM: rounded(endM),
    widthM: rounded(openingWidth),
    offsetM: rounded(offset.alongM),
    reasons: Object.freeze(reasons),
  });
}

function intervalsOverlap(intervals) {
  for (let index = 1; index < intervals.length; index += 1) {
    if (intervals[index].startM < intervals[index - 1].endM - EPSILON) return true;
  }
  return false;
}

function wallSegment(wall, startM, endM, index) {
  const widthM = endM - startM;
  if (widthM < MIN_SEGMENT_M) return null;
  const center = localToWorld(wall, (startM + endM) / 2);
  return baseElement(wall, {
    id: `${wall.id}::segment:${index}`,
    sourceWallId: wall.id,
    type: "wall",
    centerXM: center.centerXM,
    centerYM: center.centerYM,
    widthM: rounded(widthM),
    depthM: rounded(wall.depthM),
    rotationDeg: rounded(wall.rotationDeg, 3),
    derivedPassageSegment: true,
    coordinateAuthority: wall.coordinateAuthority,
  });
}

function lintelElement(wall, opening, interval) {
  const wallHeight = Math.max(DEFAULT_WALL_HEIGHT_M, finite(wall.heightM, DEFAULT_WALL_HEIGHT_M));
  const doorHeight = Math.min(
    wallHeight,
    Math.max(1.7, finite(opening.heightM, DEFAULT_DOOR_HEIGHT_M)),
  );
  const lintelHeight = wallHeight - doorHeight;
  if (lintelHeight < MIN_SEGMENT_M) return null;
  const center = localToWorld(wall, interval.offsetM);
  return baseElement(wall, {
    id: `${wall.id}::lintel:${opening.id}`,
    sourceWallId: wall.id,
    sourceOpeningId: opening.id,
    type: "wall_lintel",
    centerXM: center.centerXM,
    centerYM: center.centerYM,
    widthM: interval.widthM,
    depthM: rounded(wall.depthM),
    rotationDeg: rounded(wall.rotationDeg, 3),
    renderHeightM: rounded(lintelHeight),
    renderBaseM: rounded(doorHeight),
    derivedPassageSegment: true,
    coordinateAuthority: wall.coordinateAuthority,
  });
}

function passageMarker(opening) {
  return baseElement(opening, {
    id: `${opening.id}::passage-marker`,
    type: opening.type === "emergency_exit"
      ? "emergency_exit_passage"
      : "door_passage",
    sourceOpeningId: opening.id,
    renderHeightM: 0.035,
    renderBaseM: 0.0175,
    derivedPassageMarker: true,
    passable: true,
  });
}

function passableOpeningsForWall(architecture, wall) {
  return architecture.filter((row) => (
    PASSAGE_TYPES.has(text(row?.type).toLowerCase())
    && text(row?.parentId) === text(wall.id)
    && text(row?.hostConstraint) === "wall_centerline_v1"
  ));
}

export function buildPlanogramWallPassageModel(architecture = []) {
  const source = Array.isArray(architecture) ? architecture.filter(Boolean) : [];
  const walls = source.filter((row) => text(row?.type).toLowerCase() === "wall");
  const wallIds = new Set(walls.map((row) => text(row.id)));
  const passableOpeningIds = new Set();
  const renderArchitecture = [];
  const navigationArchitecture = [];
  const diagnostics = [];
  let passageCount = 0;
  let segmentedWallCount = 0;

  for (const wall of walls) {
    const openings = passableOpeningsForWall(source, wall);
    if (!openings.length) {
      renderArchitecture.push(baseElement(wall));
      navigationArchitecture.push(baseElement(wall));
      continue;
    }
    const intervals = openings
      .map((opening) => ({ opening, validation: passageValidation(wall, opening) }))
      .sort((left, right) => (
        left.validation.startM - right.validation.startM
        || text(left.opening.id).localeCompare(text(right.opening.id))
      ));
    const invalid = intervals.filter((row) => !row.validation.valid);
    const validIntervals = intervals.map((row) => row.validation);
    if (invalid.length || intervalsOverlap(validIntervals)) {
      renderArchitecture.push(baseElement(wall));
      navigationArchitecture.push(baseElement(wall));
      for (const row of invalid) {
        diagnostics.push(Object.freeze({
          wallId: text(wall.id),
          openingId: text(row.opening.id),
          reasons: row.validation.reasons,
          failClosed: true,
        }));
      }
      if (!invalid.length && intervalsOverlap(validIntervals)) {
        diagnostics.push(Object.freeze({
          wallId: text(wall.id),
          openingId: null,
          reasons: Object.freeze(["passage_intervals_overlap"]),
          failClosed: true,
        }));
      }
      continue;
    }

    const wallStart = -finite(wall.widthM) / 2;
    const wallEnd = finite(wall.widthM) / 2;
    let cursor = wallStart;
    let segmentIndex = 0;
    for (const row of intervals) {
      const segment = wallSegment(wall, cursor, row.validation.startM, segmentIndex++);
      if (segment) {
        renderArchitecture.push(segment);
        navigationArchitecture.push(segment);
      }
      const lintel = lintelElement(wall, row.opening, row.validation);
      if (lintel) renderArchitecture.push(lintel);
      renderArchitecture.push(passageMarker(row.opening));
      passableOpeningIds.add(text(row.opening.id));
      passageCount += 1;
      cursor = row.validation.endM;
    }
    const finalSegment = wallSegment(wall, cursor, wallEnd, segmentIndex);
    if (finalSegment) {
      renderArchitecture.push(finalSegment);
      navigationArchitecture.push(finalSegment);
    }
    segmentedWallCount += 1;
  }

  for (const row of source) {
    const type = text(row?.type).toLowerCase();
    if (type === "wall") continue;
    if (passableOpeningIds.has(text(row.id))) continue;
    const normalized = baseElement(row);
    renderArchitecture.push(normalized);
    navigationArchitecture.push(normalized);
  }

  return Object.freeze({
    contract: PLANOGRAM_WALL_PASSAGE_CONTRACT,
    productionReleaseAllowed: false,
    storeDnaAuthority: false,
    passageCount,
    segmentedWallCount,
    invalidPassageCount: diagnostics.length,
    renderArchitecture: Object.freeze(renderArchitecture),
    navigationArchitecture: Object.freeze(navigationArchitecture),
    diagnostics: Object.freeze(diagnostics),
    sourceWallCount: walls.length,
    sourceHostedOpeningCount: source.filter((row) => (
      PASSAGE_TYPES.has(text(row?.type).toLowerCase()) && text(row?.parentId)
    )).length,
    wallIds: Object.freeze([...wallIds]),
  });
}
