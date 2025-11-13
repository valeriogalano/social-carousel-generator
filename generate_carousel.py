#!/usr/bin/env python3
"""
Generatore di carousel: legge testi da un file Markdown e li incolla sulle immagini
rispettando la numerazione dei file slide.

Uso base:
  python generate_carousel.py \
      --slides-dir assets/slides \
      --texts-file assets/texts.md \
      --output-dir output

Opzioni aggiuntive: --font-file, --color, --bold-color, --italic-color, --margin, --align, --valign

Formato atteso del file testi (Markdown):
  # 1
  Primo testo della slide 1

  # 2
  Testo slide 2 su una o più righe

Tutto il testo fino al prossimo titolo di livello 1 ("# <numero>") viene associato a quella slide.

Nota sul comportamento:
- Se esiste la sezione numerata nel Markdown ma il testo è vuoto, la slide viene COPIATA così com'è nell'output.
- Se NON esiste una sezione numerata corrispondente nel Markdown, la slide viene SALTATA (non viene generato alcun file).

Stili inline (tipo Markdown minimal):
- Grassetto: racchiudi tra `**` (es: `Vestibulum **lacinia**`).
- Corsivo: racchiudi tra `*` (es: `*lorem ipsum dolor*`).
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Literal

from PIL import Image, ImageDraw, ImageFont


TITLE_RE = re.compile(r"^#\s*(\d+)\s*$")


def parse_texts_md(path: Path) -> Dict[int, str]:
    """Parsa un file Markdown in sezioni numerate con pattern "# <n>".
    Ritorna un dizionario {numero_slide: testo}.
    """
    sections: Dict[int, List[str]] = {}
    current: int | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = TITLE_RE.match(raw.strip())
        if m:
            current = int(m.group(1))
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw.rstrip())
    # join and normalize whitespace (preserva righe vuote come nuove linee)
    joined: Dict[int, str] = {}
    for k, lines in sections.items():
        # rimuovi righe vuote alle estremità
        while lines and lines[0].strip() == "":
            lines.pop(0)
        while lines and lines[-1].strip() == "":
            lines.pop()
        joined[k] = "\n".join(lines).strip()
    return joined


def find_images(slides_dir: Path) -> List[Path]:
    """Trova immagini supportate nella cartella slides, ordinate per numero estratto dal nome file.
    Supporta estensioni: .png .jpg .jpeg .webp
    Nomina attesa: "<numero>.<ext>" oppure con prefissi/testi, purché contenga un intero.
    """
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in slides_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]

    def extract_index(p: Path) -> Tuple[int, str]:
        # cerca il primo intero nel nome file
        m = re.search(r"(\d+)", p.stem)
        idx = int(m.group(1)) if m else 10**9
        return idx, p.name

    files.sort(key=extract_index)
    return files


@dataclass
class RenderConfig:
    font_file: str | None
    color: str
    bold_color: str
    italic_color: str
    margin: int
    max_font_size: int
    min_font_size: int
    valign: str  # top, center, bottom
    align: str  # left, center
    italic_skew_deg: float


def load_font(cfg: RenderConfig, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Prova truetype indicato; in alternativa tenta DejaVuSans; fallback a default bitmap
    if cfg.font_file:
        try:
            return ImageFont.truetype(cfg.font_file, size=size)
        except Exception:
            pass
    for candidate in ("DejaVuSans.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


TokenStyle = Literal["normal", "bold", "italic"]


def _parse_tokens_line(line: str) -> List[Tuple[str, TokenStyle]]:
    """Parsa una riga con markup minimale tipo Markdown.
    Supporta:
    - **grassetto**
    - *corsivo*
    Restituisce tokens (word, style).
    """
    tokens: List[Tuple[str, TokenStyle]] = []

    # Stato semplice: normal/bold/italic, niente annidamento (se annidato, si comporta in modo best-effort)
    style: TokenStyle = "normal"
    buf: List[str] = []
    i = 0
    while i < len(line):
        if line.startswith("**", i):
            # flush corrente
            if buf:
                for w in "".join(buf).split():
                    if w:
                        tokens.append((w, style))
                buf = []
            style = "normal" if style == "bold" else ("bold" if style == "normal" else style)
            i += 2
            continue
        if line.startswith("*", i):
            if buf:
                for w in "".join(buf).split():
                    if w:
                        tokens.append((w, style))
                buf = []
            style = "normal" if style == "italic" else ("italic" if style == "normal" else style)
            i += 1
            continue
        buf.append(line[i])
        i += 1
    if buf:
        for w in "".join(buf).split():
            if w:
                tokens.append((w, style))
    return tokens


def _tokenize_text(text: str) -> List[List[Tuple[str, TokenStyle]]]:
    """Converte il testo in una lista di paragrafi; ogni paragrafo è lista di tokens.
    Le righe vuote generano paragrafi vuoti (linea vuota nell'output).
    """
    paragraphs: List[List[Tuple[str, TokenStyle]]] = []
    for raw in text.split("\n"):
        if raw.strip() == "":
            paragraphs.append([])  # linea vuota
        else:
            paragraphs.append(_parse_tokens_line(raw))
    return paragraphs


def _token_width(draw: ImageDraw.ImageDraw, word: str, font: ImageFont.ImageFont, style: TokenStyle, line_h: int, italic_skew_deg: float) -> float:
    import math
    base = draw.textlength(word, font=font)
    if style == "italic":
        sh = abs(math.tan(math.radians(italic_skew_deg)))
        return base + sh * line_h
    return base


def _wrap_rich_tokens(
    draw: ImageDraw.ImageDraw,
    tokens: Iterable[Tuple[str, TokenStyle]],
    font: ImageFont.ImageFont,
    max_width: int,
    line_h: int,
    italic_skew_deg: float,
) -> List[List[Tuple[str, TokenStyle]]]:
    """Esegue il wrapping di una sequenza di token in righe (liste di token)."""
    lines: List[List[Tuple[str, TokenStyle]]] = []
    line: List[Tuple[str, TokenStyle]] = []
    width = 0.0
    space_w = draw.textlength(" ", font=font)
    for word, sty in tokens:
        tw = _token_width(draw, word, font, sty, line_h, italic_skew_deg)
        add_w = tw + (space_w if line else 0.0)
        if line and width + add_w > max_width:
            lines.append(line)
            line = [(word, sty)]
            width = _token_width(draw, word, font, sty, line_h, italic_skew_deg)
        else:
            if line:
                width += space_w
            width += tw
            line.append((word, sty))
    if line or not lines:
        lines.append(line)
    return lines


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, line_h: int, italic_skew_deg: float) -> List[List[Tuple[str, TokenStyle]]]:
    """Effettua wrapping conservando i token e gli stili. Ritorna lista di righe."""
    paragraphs = _tokenize_text(text)
    all_lines: List[List[Tuple[str, TokenStyle]]] = []
    for para in paragraphs:
        if not para:  # linea vuota
            all_lines.append([])
            continue
        lines = _wrap_rich_tokens(draw, para, font, max_width, line_h, italic_skew_deg)
        all_lines.extend(lines)
    return all_lines


def fit_text_in_box(draw: ImageDraw.ImageDraw, text: str, cfg: RenderConfig, box_w: int, box_h: int) -> Tuple[ImageFont.ImageFont, List[List[Tuple[str, TokenStyle]]]]:
    """Riduce la dimensione del font finché il testo wrappato entra nel box.
    Restituisce (font, righe_token).
    """
    size = cfg.max_font_size
    while size >= cfg.min_font_size:
        font = load_font(cfg, size)
        # misura blocco
        ascent, descent = getattr(font, "getmetrics", lambda: (size, int(size*0.25)))()
        line_h = ascent + descent
        spacing = int(size * 0.25)
        wrapped_lines = wrap_text(draw, text, font, max_width=box_w, line_h=line_h, italic_skew_deg=cfg.italic_skew_deg)
        non_empty = [ln for ln in wrapped_lines]
        # calcolo altezza: ogni linea (anche vuota) occupa line_h, tra linee aggiungi spacing
        h = len(non_empty) * line_h + max(0, len(non_empty) - 1) * spacing
        # stima larghezza massima della linea
        max_w = 0
        for ln in wrapped_lines:
            # calcola la larghezza somma dei token (con eventuale skew italico) + spazi
            lw = 0.0
            for i, (t, sty) in enumerate(ln):
                if i:
                    lw += draw.textlength(" ", font=font)
                lw += _token_width(draw, t, font, sty, line_h, cfg.italic_skew_deg)
            max_w = max(max_w, int(lw))
        w = max_w
        if w <= box_w and h <= box_h:
            return font, wrapped_lines
        size = max(cfg.min_font_size, size - 2)
        if size == cfg.min_font_size:
            # prova ultima volta
            font = load_font(cfg, size)
            ascent, descent = getattr(font, "getmetrics", lambda: (size, int(size*0.25)))()
            line_h = ascent + descent
            spacing = int(size * 0.25)
            wrapped_lines = wrap_text(draw, text, font, max_width=box_w, line_h=line_h, italic_skew_deg=cfg.italic_skew_deg)
            h = len(wrapped_lines) * line_h + max(0, len(wrapped_lines) - 1) * spacing
            max_w = 0
            for ln in wrapped_lines:
                lw = 0.0
                for i, (t, sty) in enumerate(ln):
                    if i:
                        lw += draw.textlength(" ", font=font)
                    lw += _token_width(draw, t, font, sty, line_h, cfg.italic_skew_deg)
                max_w = max(max_w, int(lw))
            w = max_w
            if w <= box_w and h <= box_h:
                return font, wrapped_lines
            break
    f = load_font(cfg, cfg.min_font_size)
    ascent, descent = getattr(f, "getmetrics", lambda: (f.size, int(f.size*0.25)))()
    return f, wrap_text(draw, text, f, max_width=box_w, line_h=ascent+descent, italic_skew_deg=cfg.italic_skew_deg)


def render_on_image(img_path: Path, text: str, out_path: Path, cfg: RenderConfig) -> None:
    im = Image.open(img_path).convert("RGBA")
    W, H = im.size
    draw = ImageDraw.Draw(im)

    margin = cfg.margin
    box_w = W - 2 * margin
    box_h = H - 2 * margin

    font, lines = fit_text_in_box(draw, text, cfg, box_w, box_h)
    spacing = int(font.size * 0.25)
    ascent, descent = getattr(font, "getmetrics", lambda: (font.size, int(font.size*0.25)))()
    line_h = ascent + descent

    # calcolo altezza totale
    th = len(lines) * line_h + max(0, len(lines) - 1) * spacing

    # x base per allineamento a sinistra
    left_x = margin

    if cfg.valign == "top":
        y = margin
    elif cfg.valign == "bottom":
        y = H - margin - th
    else:
        y = (H - th) // 2

    # Disegna riga per riga, token per token (applicando stili)
    space_w = draw.textlength(" ", font=font)
    for line_tokens in lines:
        # Larghezza effettiva della riga (stringa unita con spazi)
        lw = 0.0
        for i, (t, sty) in enumerate(line_tokens):
            if i:
                lw += space_w
            lw += _token_width(draw, t, font, sty, line_h, cfg.italic_skew_deg)
        line_w = int(lw)
        if cfg.align == "center":
            x = (W - line_w) // 2
        else:
            x = left_x

        # Disegna i token
        for idx, (tok, sty) in enumerate(line_tokens):
            if sty == "bold":
                # colore grassetto
                fill_color = cfg.bold_color
                # finto bold: multiple pass (senza contorno/stroke)
                for ox, oy in ((0,0), (1,0), (0,1), (1,1)):
                    draw.text(
                        (x+ox, y+oy),
                        tok,
                        font=font,
                        fill=fill_color,
                    )
                advance = draw.textlength(tok, font=font)
            elif sty == "italic":
                # render su immagine temporanea e shear
                from PIL import Image as PILImage, ImageDraw as PILImageDraw
                import math
                pad = 2
                tw = int(draw.textlength(tok, font=font))
                temp_h = line_h + 2 * pad
                temp_w = tw + 2 * pad
                temp = PILImage.new("RGBA", (max(1, temp_w), max(1, temp_h)), (0, 0, 0, 0))
                tdraw = PILImageDraw.Draw(temp)
                tdraw.text(
                    (pad, pad),
                    tok,
                    font=font,
                    fill=cfg.italic_color or cfg.color,
                )
                sh = math.tan(math.radians(cfg.italic_skew_deg))
                new_w = int(temp_w + abs(sh) * temp_h)
                # Affine transform per shear X: (x', y') = (x + sh*y, y)
                sheared = temp.transform(
                    (max(1, new_w), max(1, temp_h)),
                    PILImage.AFFINE,
                    (1, sh, 0, 0, 1, 0),
                    resample=PILImage.BICUBIC,
                )
                im.alpha_composite(sheared, dest=(int(x), int(y - pad)))
                advance = _token_width(draw, tok, font, sty, line_h, cfg.italic_skew_deg)
            else:
                draw.text(
                    (x, y),
                    tok,
                    font=font,
                    fill=cfg.color,
                )
                advance = draw.textlength(tok, font=font)
            x += int(advance)
            if idx != len(line_tokens) - 1:
                x += int(space_w)
        y += line_h + spacing

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # salva come PNG per preservare qualità/testo; mantiene estensione originale se non PNG
    im = im.convert("RGB") if out_path.suffix.lower() in {".jpg", ".jpeg"} else im
    im.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Incolla testi su immagini in base alla numerazione")
    parser.add_argument("--slides-dir", required=True, type=Path, help="Cartella con le immagini delle slide")
    parser.add_argument("--texts-file", required=True, type=Path, help="File Markdown con i testi (sezioni '# <n>')")
    parser.add_argument("--output-dir", required=True, type=Path, help="Cartella di destinazione")
    parser.add_argument("--font-file", type=str, default=None, help="Path ad un font .ttf/.otf personalizzato")
    parser.add_argument("--color", type=str, default="#ffffff", help="Colore del testo (hex o nome)")
    parser.add_argument("--bold-color", type=str, default=None, help="Colore del testo in grassetto (**...**). Se non impostato, usa --color")
    parser.add_argument("--italic-color", type=str, default=None, help="Colore del testo in corsivo (*...*). Se non impostato, usa --color")
    parser.add_argument("--margin", type=int, default=60, help="Margine interno (px)")
    parser.add_argument("--max-font-size", type=int, default=96, help="Dimensione massima font")
    parser.add_argument("--min-font-size", type=int, default=24, help="Dimensione minima font")
    parser.add_argument("--valign", choices=["top", "center", "bottom"], default="center", help="Allineamento verticale del blocco testo")
    parser.add_argument("--align", choices=["left", "center"], default="center", help="Allineamento orizzontale delle righe")
    parser.add_argument("--italic-skew", type=float, default=12.0, help="Inclinazione del corsivo in gradi (shear X)")

    args = parser.parse_args()

    slides_dir: Path = args.slides_dir
    texts_file: Path = args.texts_file
    output_dir: Path = args.output_dir

    if not slides_dir.exists() or not slides_dir.is_dir():
        parser.error(f"Cartella slides non valida: {slides_dir}")
    if not texts_file.exists() or not texts_file.is_file():
        parser.error(f"File testi non valido: {texts_file}")

    texts = parse_texts_md(texts_file)
    images = find_images(slides_dir)

    # Colori con fallback
    bold_color = args.bold_color if args.bold_color else args.color
    italic_color = args.italic_color if args.italic_color else args.color

    cfg = RenderConfig(
        font_file=args.font_file,
        color=args.color,
        bold_color=bold_color,
        italic_color=italic_color,
        margin=int(args.margin),
        max_font_size=int(args.max_font_size),
        min_font_size=int(args.min_font_size),
        valign=args.valign,
        align=args.align,
        italic_skew_deg=float(args.italic_skew),
    )

    # mappa numero -> path immagine (ultimo vince se duplicati)
    num_to_img: Dict[int, Path] = {}
    for p in images:
        m = re.search(r"(\d+)", p.stem)
        if not m:
            continue
        num_to_img[int(m.group(1))] = p

    processed = 0
    skipped = 0  # testi senza immagine
    copied_empty = 0  # slide con sezione numerata ma testo vuoto
    skipped_no_number = 0  # slide senza sezione numerata corrispondente

    # processa tutte le immagini trovate
    for num, img_path in sorted(num_to_img.items(), key=lambda kv: kv[0]):
        out_path = output_dir / img_path.name
        if num in texts:
            if texts[num].strip():
                render_on_image(img_path, texts[num], out_path, cfg)
                processed += 1
            else:
                # se la sezione esiste ma non ha testo, copia l'immagine originale
                out_path.parent.mkdir(parents=True, exist_ok=True)
                Image.open(img_path).save(out_path)
                copied_empty += 1
        else:
            # non esiste sezione numerata corrispondente nel markdown: salta
            skipped_no_number += 1

    # warning per testi senza immagine
    for tnum in sorted(texts.keys()):
        if tnum not in num_to_img:
            skipped += 1

    print(
        f"Slides elaborate: {processed}, copiate senza testo: {copied_empty}, "
        f"saltate senza numero: {skipped_no_number}, testi senza immagine: {skipped}"
    )
    print(f"Output salvato in: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
