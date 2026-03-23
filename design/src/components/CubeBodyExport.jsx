import "./VoxelCube.css";

/**
 * Renders ONLY the cube body (no eyes, mouth, or icons) for sprite export.
 * Use at /export route — screenshot with transparent background.
 */
export default function CubeBodyExport() {
  return (
    <div
      className="voxel-scene"
      style={{ background: "transparent" }}
    >
      <div className="cube-wrapper">
        <div className="cube" style={{ transform: "rotateX(-15deg) rotateY(-25deg)" }}>
          {/* Front face — empty, no face-inner */}
          <div className="cube-face front">
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          {/* Top face */}
          <div className="cube-face top">
            <div className="face-shading top-shade" />
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          {/* Right face */}
          <div className="cube-face right">
            <div className="face-shading right-shade" />
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          <div className="cube-face left" />
          <div className="cube-face back" />
          <div className="cube-face bottom" />
        </div>
      </div>
    </div>
  );
}
