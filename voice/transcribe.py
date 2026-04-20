def parse_multipart(headers, rfile):
    """Izvuci prvi fajl iz multipart/form-data requesta."""
    content_type = headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        return None, None
    boundary = content_type.split("boundary=")[-1].strip().encode()
    length = int(headers.get("Content-Length", "0"))
    body = rfile.read(length)
    delimiter = b"--" + boundary
    parts = body.split(delimiter)
    for part in parts[1:]:
        if part in (b"--\r\n", b"--", b"\r\n", b""):
            continue
        if b"\r\n\r\n" in part:
            raw_headers, file_data = part.split(b"\r\n\r\n", 1)
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]
            header_text = raw_headers.decode("utf-8", errors="replace")
            filename = "recording.webm"
            for header_line in header_text.split("\r\n"):
                if "filename=" in header_line:
                    fname_part = header_line.split("filename=")[-1].strip().strip('"')
                    if fname_part:
                        filename = fname_part
            return filename, file_data
    return None, None


def transcribe_audio(client, filename, audio_data):
    """Transkribuj audio koristeci Whisper via Groq."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
    mime = f"audio/{ext}"
    response = client.audio.transcriptions.create(
        file=(filename, audio_data, mime),
        model="whisper-large-v3-turbo",
    )
    return response.text
