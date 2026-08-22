import {
  buildPlanogramAuthoringDocument,
  buildStoreScene,
  candidateFromReviewedStoreScan,
  createStoreSceneHistory,
  executeStoreSceneCommand,
  findStoreSceneAisleViolations,
  findStoreSceneCollisions,
  redoStoreSceneCommand,
  serializeStoreScene,
  undoStoreSceneCommand,
} from "./planogramAuthoringModel.js";

export const PLANOGRAM_CAD_SESSION_CONTRACT = "eay.planogram.cad-session.v1";

function diagnostics(scene, minimumAisleM) {
  const collisions = findStoreSceneCollisions(scene, ["fixture", "wall", "column", "no_go", "technical"]);
  const aisleViolations = findStoreSceneAisleViolations(scene, minimumAisleM, ["fixture"]);
  return Object.freeze({
    collisionCount: collisions.length,
    aisleViolationCount: aisleViolations.length,
    collisions: Object.freeze(collisions),
    aisleViolations: Object.freeze(aisleViolations),
  });
}

function sessionFromHistory(base, history) {
  return Object.freeze({
    ...base,
    history,
    scene: history.present,
    serializedScene: serializeStoreScene(history.present),
    diagnostics: diagnostics(history.present, base.minimumAisleM),
  });
}

export function createPlanogramCadSession({ candidate = null, reviewedResult = null, minimumAisleM = 1, sceneId = null } = {}) {
  const editableCandidate = reviewedResult
    ? candidateFromReviewedStoreScan(candidate, reviewedResult)
    : candidate;
  if (!editableCandidate) return null;
  const document = buildPlanogramAuthoringDocument(editableCandidate);
  if (!document) return null;
  const scene = buildStoreScene(editableCandidate, document, sceneId ? { sceneId } : {});
  if (!scene) return null;
  const sourceKind = reviewedResult ? "human_reviewed_store_scan" : "authored_store_scene";
  const base = Object.freeze({
    contract: PLANOGRAM_CAD_SESSION_CONTRACT,
    sourceKind,
    candidate: editableCandidate,
    document,
    minimumAisleM: Math.max(0.8, Number(minimumAisleM) || 1),
    previewOnly: Boolean(scene.previewOnly),
    geometryAuthority: scene.previewOnly ? "editable_preview_not_store_dna_authority" : "editable_store_scene",
    productionReleaseAllowed: false,
    physicalTruthAttested: false,
    reviewFingerprint: scene.provenance?.reviewFingerprint || null,
  });
  return sessionFromHistory(base, createStoreSceneHistory(scene));
}

export function executePlanogramCadSessionCommand(session, command) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) return session;
  return sessionFromHistory(session, executeStoreSceneCommand(session.history, command));
}

export function undoPlanogramCadSession(session) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) return session;
  return sessionFromHistory(session, undoStoreSceneCommand(session.history));
}

export function redoPlanogramCadSession(session) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) return session;
  return sessionFromHistory(session, redoStoreSceneCommand(session.history));
}
