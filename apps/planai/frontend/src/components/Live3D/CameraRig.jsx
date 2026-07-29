import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { Vector3 } from "three";

const PRESETS = {
  overview: { pos: [8, 7, 9], target: [2, 0.7, -2] },
  top: { pos: [3, 12, 0.01], target: [3, 0, -2] },
  chilled: { pos: [6, 4, 5], target: [6, 1, -1] },
  frozen: { pos: [8, 4, 4], target: [8, 1, -1] },
  dispatch: { pos: [-2, 4, 5], target: [0, 0.5, 0] },
};

export default function CameraRig({ preset = "overview", controlsRef }) {
  const { camera } = useThree();
  useEffect(() => {
    const next = PRESETS[preset] || PRESETS.overview;
    camera.position.lerp(new Vector3(...next.pos), 0.8);
    camera.lookAt(...next.target);
    if (controlsRef?.current) {
      controlsRef.current.target.set(...next.target);
      controlsRef.current.update();
    }
  }, [preset, camera, controlsRef]);
  return null;
}
