# Local fallback for imghdr (removed from Python 3.13)
def what(file, h=None):
    if h is None:
        if isinstance(file, str):
            with open(file, "rb") as f:
                h = f.read(32)
        else:
            h = file.read(32)

    if h.startswith(b'\211PNG\r\n\032\n'):
        return 'png'
    if h.startswith(b'\377\330'):
        return 'jpeg'
    if h[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if h.startswith(b'BM'):
        return 'bmp'
    if h.startswith(b'II*\000') or h.startswith(b'MM\000*'):
        return 'tiff'
    if h.startswith(b'RIFF') and h[8:12] == b'WEBP':
        return 'webp'
    return None