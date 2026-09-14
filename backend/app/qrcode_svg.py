"""QR codes for gate verification. Uses segno (pure Python, no native deps)
when available; otherwise falls back to a clear SVG token card so the
endpoint never fails.
"""

def qr_svg(payload: str) -> str:
    try:
        import segno
        import io
        buf = io.BytesIO()
        segno.make(payload, error="l").save(buf, kind="svg", scale=8, border=2)
        return buf.getvalue().decode()
    except ImportError:
        token = payload.split(":")[-1]
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">'
            '<rect width="240" height="240" rx="16" fill="#0b3d2e"/>'
            f'<text x="120" y="105" text-anchor="middle" fill="white" font-size="26" font-family="monospace">{token}</text>'
            '<text x="120" y="135" text-anchor="middle" fill="#f2b134" font-size="14" font-family="sans-serif">Mandi Mitra gate pass</text>'
            '<text x="120" y="160" text-anchor="middle" fill="#9db8ac" font-size="11" font-family="sans-serif">show this at the gate</text>'
            "</svg>"
        )
