/**
 * Browser device fingerprinting for rate-limit resilience.
 *
 * Generates a stable SHA-256 hash from a set of browser characteristics
 * that remain constant across page loads. This fingerprint is sent as
 * the `X-Device-Fingerprint` header so the backend can build a composite
 * rate-limit key (fingerprint + IP) that survives IP rotation on mobile
 * networks (5G, carrier-grade NAT).
 *
 * No external library is needed — everything relies on standard Web APIs.
 */

function getCanvasFingerprint(): string {
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) return '';
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillText('fingerprint', 2, 2);
        return canvas.toDataURL().slice(-50);
    } catch {
        return '';
    }
}

/**
 * Build a SHA-256 hex digest from stable browser characteristics.
 *
 * The resulting hash is deterministic for a given browser/device
 * combination but does not contain any PII in cleartext.
 */
export async function generateFingerprint(): Promise<string> {
    const components: (string | number | undefined)[] = [
        navigator.language,
        navigator.languages?.join(','),
        screen.width + 'x' + screen.height,
        screen.colorDepth,
        new Date().getTimezoneOffset(),
        navigator.hardwareConcurrency,
        navigator.maxTouchPoints,
        getCanvasFingerprint(),
    ];

    const raw = components.filter(Boolean).join('|');

    const encoder = new TextEncoder();
    const data = encoder.encode(raw);
    const hash = await crypto.subtle.digest('SHA-256', data);

    return Array.from(new Uint8Array(hash))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
}
