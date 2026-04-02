import styles from './texture-overlay.module.css';

export function TextureOverlay() {
  return (
    <div className={styles.overlay}>
      <svg className={styles.svg} xmlns="http://www.w3.org/2000/svg">
        <filter id="noise">
          <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#noise)" />
      </svg>
    </div>
  );
}
