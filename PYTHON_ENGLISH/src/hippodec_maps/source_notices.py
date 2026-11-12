"""Cartographic source credit and technical-use notice."""
from __future__ import annotations
import textwrap

MITECO_SOURCE = '© Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO)'
DEMARCATION_NOTICE = 'This map is for technical use only and must not be regarded as the official delimitation of borders between neighbouring countries.'

def add_cartographic_notice(figure) -> None:
    """Add one readable source note below the plotted figure, without changing axes."""
    if any(text.get_gid() == "hispa-cartographic-notice" for text in figure.texts):
        return
    width = max(54, int(figure.get_figwidth() * 15))
    newline = chr(10)
    text = newline.join(textwrap.wrap('Cartographic source: ' + MITECO_SOURCE, width=width))
    text += newline + newline.join(textwrap.wrap(DEMARCATION_NOTICE, width=width))
    figure.text(0.015, -0.085, text, ha="left", va="top", fontsize=7,
                color="#4b5563", gid="hispa-cartographic-notice", clip_on=False)
